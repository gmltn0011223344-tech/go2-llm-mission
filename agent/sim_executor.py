"""
agent/sim_executor.py

로봇 없이 임무 루프를 돌리기 위한 가짜 실행부.
지정한 시나리오대로 상태값을 뱉습니다. Rule vs LLM 비교 실험과
주말 오프라인 테스트에 사용합니다.

사용법:
    exec = SimExecutor(scripted={"BLUE": "NO_PATH", "LAPTOP": "TARGET_NOT_FOUND"})
    runner = MissionRunner(exec, decision_mode="llm")
    runner.run("빨간 지점을 지나 파란 지점에서 노트북 확인하고 돌아와")

scripted에 없는 목표는 기본적으로 성공(REACHED/TARGET_FOUND) 처리됩니다.
같은 목표를 다시 실행하면(재시도/재계획) 두 번째부터는 성공하도록 해서,
'재시도하면 풀리는' 상황도 표현할 수 있습니다.
"""


class SimExecutor:
    def __init__(self, scripted=None, recover_on_retry=True):
        self.scripted = scripted or {}
        self.recover_on_retry = recover_on_retry
        self.seen = {}   # target별 실행 횟수

    def __call__(self, task: dict) -> str:
        action = task.get("action")
        target = task.get("target")

        self.seen[target] = self.seen.get(target, 0) + 1
        attempt = self.seen[target]

        # 복귀/정지류는 항상 성공으로 간주
        if action == "RETURN_HOME":
            return "REACHED"

        # 이 목표에 대해 미리 정해둔 실패 상태가 있는가?
        scripted_state = self.scripted.get(target)

        if scripted_state and not (self.recover_on_retry and attempt >= 2):
            # 첫 시도에서는 지정된 실패 상태를 반환
            return scripted_state

        # 지정이 없거나, 재시도로 회복된 경우 → 성공 상태
        if action == "OBSERVE":
            return "TARGET_FOUND"
        return "REACHED"
