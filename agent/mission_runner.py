"""
agent/mission_runner.py

전체 임무 루프 오케스트레이터.
자연어 명령 → 작업 분해 → 작업 실행 → 상태 수신 → 판단(AUTO/ASK) → 반복.

판단 순서 (decide)
1. 안전 규칙: ERROR·미등록 목적지는 LLM을 거치지 않음
2. 정상 상태(REACHED/TARGET_FOUND): 판단 호출 없이 계획대로 진행
3. 예외 상태: LLM(기본) 또는 Rule이 AUTO/ASK 결정
4. 출력 검증 + 재시도 한도 확인 → 실패 시 Rule 대체 → 그래도 실패하면 안전정지

ASK 처리
- ask_user(async 함수)가 있으면 질문 → 답변(RETRY/RETURN_HOME/STOP)을 행동으로 변환
- 없으면 실행하지 않고 ASK_PENDING으로 종료 (사용자 승인 전 실행 금지)

executor는 밖에서 주입: 실제 Go2(RobotExecutor) / 시뮬레이터(SimExecutor)
"""

import inspect

from agent.schema import (validate_action_output, REGISTERED_WAYPOINTS, ALLOWED_OBJECTS,
                          NORMAL_STATES, FAILURE_STATES)
from agent.rule_engine import rule_based_next_action, continue_or_stop
from agent.llm_engine import decompose_command, llm_next_action

USER_CHOICES = ("RETRY", "RETURN_HOME", "STOP")


def _norm(d, source=None):
    d = dict(d)
    d.setdefault("mode", "AUTO")
    d.setdefault("target", None)
    d.setdefault("question", None)
    d.setdefault("reason", "")
    if source:
        d["source"] = source
    d.setdefault("source", "unknown")
    return d


class MissionRunner:
    def __init__(self, executor, decision_mode="llm", max_steps=20, max_retry=1,
                 allowed_waypoints=None, allowed_objects=None, ask_user=None):
        """
        decision_mode: "llm"(기본) 또는 "rule"(API 오류 대비·참고용)
        max_retry: 같은 작업에서 AUTO로 허용하는 재시도 횟수. 초과하면 ASK
        ask_user: async def ask_user(question) -> str. 없으면 ASK에서 멈춤
        """
        self.executor = executor
        self.decision_mode = decision_mode
        self.max_steps = max_steps
        self.max_retry = max_retry
        self.allowed_waypoints = set(allowed_waypoints or REGISTERED_WAYPOINTS)
        self.allowed_objects = set(allowed_objects or ALLOWED_OBJECTS)
        self.ask_user = ask_user
        self.pending_question = None
        self.log = []

    # ------------------------------------------------------------ 판단
    def decide(self, state, context):
        ctx = dict(context)
        ctx.setdefault("max_retry", self.max_retry)
        ctx.setdefault("allowed_waypoints", sorted(self.allowed_waypoints))
        ctx.setdefault("allowed_objects", sorted(self.allowed_objects))

        if state == "ERROR" or ctx.get("registered") is False:
            return _norm(rule_based_next_action(state, ctx, self.max_retry), "safety")
        if state in NORMAL_STATES:
            return _norm(continue_or_stop(ctx.get("remaining_tasks", []), "정상 진행, 계획된 다음 작업"), "plan")

        if self.decision_mode == "rule":
            decision = rule_based_next_action(state, ctx, self.max_retry)
        else:
            try:
                decision = llm_next_action(state, ctx)
            except Exception as exc:
                decision = {"_error": f"LLM 호출/파싱 오류: {type(exc).__name__}"}

        ok, msg = self._check(decision, state, ctx)
        if ok:
            return _norm(decision)

        fallback = _norm(rule_based_next_action(state, ctx, self.max_retry), "fallback")
        fallback["reason"] = f"{msg} → Rule 대체: {fallback['reason']}"
        ok, msg2 = self._check(fallback, state, ctx)
        if ok:
            return fallback
        return _norm({"next_action": "STOP", "reason": f"검증 실패로 안전정지: {msg2}"}, "safety")

    def _check(self, d, state, ctx):
        if not isinstance(d, dict) or "_error" in d:
            return False, (d or {}).get("_error", "출력 없음") if isinstance(d, dict) else "출력 없음"
        ok, msg = validate_action_output(d, self.allowed_waypoints, self.allowed_objects)
        if not ok:
            return False, f"출력 검증 실패({msg})"
        if (d.get("mode", "AUTO") == "AUTO" and state in FAILURE_STATES
                and d.get("next_action") in ("RETRY", "OBSERVE", "MOVE_TO")
                and ctx.get("retry_count", 0) >= self.max_retry):
            return False, "재시도 한도 초과"
        return True, "ok"

    def _apply_user_answer(self, answer, current):
        a = (answer or "").strip().upper()
        if a == "RETRY" and current.get("action") in ("MOVE_TO", "OBSERVE", "RETURN_HOME"):
            return _norm({"next_action": "RETRY", "target": current.get("target"),
                          "reason": "사용자가 재시도를 승인"}, "user")
        if a == "RETURN_HOME":
            return _norm({"next_action": "RETURN_HOME", "target": "HOME",
                          "reason": "사용자가 복귀를 지시"}, "user")
        if a == "STOP":
            return _norm({"next_action": "STOP", "reason": "사용자가 정지를 지시"}, "user")
        return _norm({"next_action": "STOP", "reason": f"알 수 없는 사용자 답변({answer}) → 안전정지"}, "user")

    # ------------------------------------------------------------ 실행
    async def _execute(self, task):
        if hasattr(self.executor, "execute_async"):
            return await self.executor.execute_async(task)
        result = self.executor(task)
        return await result if inspect.isawaitable(result) else result

    def _result(self, status, steps, reason=None):
        return {"success": status == "MISSION_COMPLETED", "status": status, "steps": steps,
                "decision_mode": self.decision_mode, "question": self.pending_question,
                "reason": reason, "log": self.log}

    async def run(self, nl_command):
        tasks = decompose_command(nl_command).get("tasks", [])
        if not tasks:
            return self._result("FAILED", 0, "작업 분해 실패")

        for task in tasks:
            ok, msg = validate_action_output(
                {"next_action": task.get("action"), "target": task.get("target")},
                self.allowed_waypoints, self.allowed_objects)
            if not ok:
                # 미등록 목적지·물체가 포함된 계획은 실행하지 않고 사용자에게 확인
                self.pending_question = (f"명령을 실행할 수 없습니다({msg}). "
                                         f"등록된 목적지 {sorted(self.allowed_waypoints)} 중에서 다시 지시해 주세요.")
                return self._result("ASK_PENDING", 0, "초기 작업 계획 검증 실패")

        queue, retry_count, steps = list(tasks), 0, 0
        status, failure_before_return = "RUNNING", False

        while queue and steps < self.max_steps:
            steps += 1
            current = queue.pop(0)
            state = await self._execute(current)
            context = {"current_action": current.get("action"),
                       "current_target": current.get("target"),
                       "retry_count": retry_count,
                       "remaining_tasks": list(queue)}
            decision = self.decide(state, context)

            entry = {"step": steps, "executed": current, "state": state,
                     "mode": decision["mode"], "source": decision["source"],
                     "next_action": decision["next_action"], "next_target": decision["target"],
                     "question": decision["question"], "reason": decision["reason"]}
            self.log.append(entry)

            user_approved = False
            if decision["mode"] == "ASK":
                if self.ask_user is None:
                    self.pending_question = decision["question"]
                    status = "ASK_PENDING"
                    break
                answer = await self.ask_user(decision["question"])
                decision = self._apply_user_answer(answer, current)
                entry.update({"user_answer": answer, "next_action": decision["next_action"],
                              "next_target": decision["target"],
                              "reason": entry["reason"] + f" / 사용자 답변: {decision['reason']}"})
                user_approved = True

            nxt = decision["next_action"]
            if nxt == "STOP":
                if failure_before_return and current.get("action") == "RETURN_HOME" and state == "REACHED":
                    status = "SAFE_RETURN"
                elif state in NORMAL_STATES and not queue:
                    status = "MISSION_COMPLETED"
                else:
                    status = "STOPPED"
                break
            if nxt == "RETURN_HOME":
                if current.get("action") == "RETURN_HOME" and state == "REACHED":
                    status = "SAFE_RETURN" if failure_before_return else "MISSION_COMPLETED"
                    break
                if state not in NORMAL_STATES:
                    failure_before_return = True
                queue, retry_count = [{"action": "RETURN_HOME", "target": "HOME"}], 0
                continue
            if nxt == "RETRY":
                retry_count += 1
                queue.insert(0, current)
                continue
            if nxt in ("MOVE_TO", "OBSERVE"):
                if state in NORMAL_STATES:
                    retry_count = 0          # 다음 작업은 이미 큐에 있음
                else:
                    retry_count += 1
                    queue.insert(0, {"action": nxt, "target": decision["target"]})
                continue

        if status == "RUNNING":
            status = "FAILED" if steps >= self.max_steps and queue else "MISSION_COMPLETED"
        return self._result(status, steps)
