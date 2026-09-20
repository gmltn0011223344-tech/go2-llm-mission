"""
agent/mission_runner.py

전체 임무 루프를 담당하는 오케스트레이터.
자연어 명령 → LLM 작업 분해 → (작업 하나씩) 실행 → 상태 수신 →
Rule 또는 LLM으로 다음 행동 결정 → 반복.

핵심 설계:
- 이 파일은 '로봇을 어떻게 실행하는지' 세부는 모릅니다. executor(실행 함수)를
  밖에서 주입받습니다. 그래서 (1) 실제 Go2 (2) 가짜 시뮬레이터 둘 다에서
  똑같이 돌아갑니다. → 발표용 비교 실험을 로봇 없이도 만들 수 있음.
- decision_mode="rule" 또는 "llm" 으로 같은 시나리오를 두 방식으로 돌려
  결과를 비교합니다. (발표의 핵심 근거)
"""

import inspect

from agent.schema import validate_action_output
from agent.rule_engine import rule_based_next_action
from agent.llm_engine import decompose_command, llm_next_action


class MissionRunner:
    def __init__(
        self,
        executor,
        decision_mode="llm",
        max_steps=20,
        max_retry=1,
        allowed_waypoints=None,
    ):
        """
        executor: 함수. executor(action_dict) -> 표준 상태 문자열(REACHED 등)을 반환.
                  실제 로봇용/시뮬용을 밖에서 갈아끼움.
        decision_mode: "rule" 또는 "llm"
        max_steps: 무한루프 방지용 최대 스텝 수
        max_retry: 한 작업당 허용 재시도 횟수
        """
        self.executor = executor
        self.decision_mode = decision_mode
        self.max_steps = max_steps
        self.max_retry = max_retry
        self.allowed_waypoints = set(allowed_waypoints or {"A", "B", "RED", "BLUE", "GREEN", "HOME"})
        self.log = []   # 각 스텝 기록 (발표/보고서용)

    def _decide(self, state, context):
        if self.decision_mode == "rule":
            return rule_based_next_action(state, context)
        return llm_next_action(state, context)

    async def _execute(self, task: dict) -> str:
        if hasattr(self.executor, "execute_async"):
            return await self.executor.execute_async(task)
        result = self.executor(task)
        if inspect.isawaitable(result):
            return await result
        return result

    def _safe_decide(self, state, context):
        """LLM 출력이 잘못되면 Rule로 대체하고, 그것도 실패하면 정지한다."""
        try:
            decision = self._decide(state, context)
        except Exception as exc:
            decision = {"next_action": "STOP", "target": None,
                        "reason": f"LLM 호출/파싱 오류: {type(exc).__name__}"}

        ok, msg = validate_action_output(decision, self.allowed_waypoints)
        fallback_used = False
        if not ok and self.decision_mode == "llm":
            fallback_used = True
            decision = rule_based_next_action(state, context)
            ok, fallback_msg = validate_action_output(decision, self.allowed_waypoints)
            msg = f"LLM 출력 오류({msg}) → Rule 대체: {fallback_msg}"

        if not ok:
            fallback_used = True
            decision = {"next_action": "STOP", "target": None,
                        "reason": f"출력 검증 실패로 안전정지: {msg}"}
            ok, msg = True, "안전정지로 대체"
        return decision, ok, msg, fallback_used

    async def run(self, nl_command: str) -> dict:
        # 1) 자연어 → 작업 목록
        plan = decompose_command(nl_command)
        tasks = plan.get("tasks", [])
        if not tasks:
            return {"success": False, "status": "FAILED",
                    "reason": "작업 분해 실패", "log": self.log}

        for task in tasks:
            candidate = {
                "next_action": task.get("action"),
                "target": task.get("target"),
                "reason": "초기 작업 계획 검증",
            }
            ok, msg = validate_action_output(candidate, self.allowed_waypoints)
            if not ok:
                return {"success": False, "status": "FAILED",
                        "reason": f"초기 작업 계획 검증 실패: {msg}", "log": self.log}

        # 2) 작업 큐를 하나씩 실행
        queue = list(tasks)
        retry_count = 0
        steps = 0
        terminal_status = "RUNNING"
        failure_before_return = False

        while queue and steps < self.max_steps:
            steps += 1
            current = queue.pop(0)

            # 현재 작업 실행 → 표준 상태 수신
            state = await self._execute(current)

            context = {
                "current_target": current.get("target"),
                "retry_count": retry_count,
                "remaining_tasks": queue,
            }

            # 상태 기반 다음 행동 결정
            decision, ok, msg, fallback_used = self._safe_decide(state, context)

            self.log.append({
                "step": steps,
                "executed": current,
                "state": state,
                "decision_mode": self.decision_mode,
                "next_action": decision.get("next_action"),
                "next_target": decision.get("target"),
                "reason": decision.get("reason"),
                "valid": ok,
                "valid_msg": msg,
                "fallback_used": fallback_used,
            })

            nxt = decision.get("next_action")

            # ---- 결정된 다음 행동을 큐에 반영 ----
            if nxt == "STOP":
                if failure_before_return and current.get("action") == "RETURN_HOME" and state == "REACHED":
                    terminal_status = "SAFE_RETURN"
                elif state in ("REACHED", "TARGET_FOUND") and not queue:
                    terminal_status = "MISSION_COMPLETED"
                else:
                    terminal_status = "STOPPED"
                break
            if nxt == "RETURN_HOME":
                if current.get("action") == "RETURN_HOME" and state == "REACHED":
                    terminal_status = "SAFE_RETURN" if failure_before_return else "MISSION_COMPLETED"
                    break
                if state not in ("REACHED", "TARGET_FOUND"):
                    failure_before_return = True
                # 복귀를 마지막 작업으로 넣고 재시도 카운트 초기화
                queue = [{"action": "RETURN_HOME", "target": "HOME"}]
                retry_count = 0
                continue
            if nxt == "RETRY":
                if retry_count >= self.max_retry:
                    terminal_status = "STOPPED"
                    break
                retry_count += 1
                queue.insert(0, current)   # 방금 작업을 다시 앞에 넣음
                continue
            if nxt in ("MOVE_TO", "OBSERVE"):
                # 재계획: 새 목표로 현재 작업을 대체해 다시 시도
                new_task = {"action": nxt, "target": decision.get("target")}
                # 원래 목표와 같으면 정상 진행(다음 작업), 다르면 재계획으로 간주
                if state in ("REACHED", "TARGET_FOUND"):
                    retry_count = 0            # 성공적으로 진행
                else:
                    if retry_count >= self.max_retry:
                        terminal_status = "STOPPED"
                        break
                    retry_count += 1
                    queue.insert(0, new_task)  # 재계획된 작업 먼저 수행
                continue

        if steps >= self.max_steps and terminal_status == "RUNNING":
            terminal_status = "FAILED"
        elif not queue and terminal_status == "RUNNING":
            terminal_status = "MISSION_COMPLETED"

        return {
            "success": terminal_status == "MISSION_COMPLETED",
            "status": terminal_status,
            "steps": steps,
            "decision_mode": self.decision_mode,
            "log": self.log,
        }
