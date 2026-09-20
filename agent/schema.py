"""
Go2 자연어 임무 시스템 - 행동/상태 스키마

행동(Action)은 딱 5개로 제한합니다. LLM이든 Rule이든 이 5개 밖의 값을
내면 그 자체로 '실패'로 채점할 수 있게 하기 위해서입니다.
"""

# 로봇이 실제로 실행 가능한 행동 (Go2 실행부에 그대로 전달되는 값)
ACTIONS = [
    "MOVE_TO",      # target으로 이동 (재계획도 이걸로 표현: 새로운 target을 주면 됨)
    "OBSERVE",      # 현재 위치에서 target 물체를 확인
    "RETRY",        # 방금 하던 작업을 한 번 더 시도
    "RETURN_HOME",  # 시작 지점으로 복귀
    "STOP",         # 안전 정지 (실패 보고)
]

# 실행부(다령 담당)로부터 들어오는 상태값
STATES = [
    "REACHED",           # 목적지 도착
    "NO_PATH",           # 경로를 찾을 수 없음
    "TIMEOUT",           # 이동/행동 시간 초과
    "TARGET_FOUND",      # OBSERVE 결과 물체를 찾음
    "TARGET_NOT_FOUND",  # OBSERVE 결과 물체를 못 찾음
    "ERROR",             # 그 외 오류
]


def validate_action_output(
    output: dict,
    allowed_waypoints: set[str] | None = None,
) -> tuple[bool, str]:
    """
    LLM/Rule이 내놓은 다음-행동 JSON이 스키마를 지키는지 검사.
    지금 단계에서 제일 중요한 안전장치 — 이게 없으면 LLM이 이상한 값을
    내도 그냥 통과되어 버립니다.
    """
    if not isinstance(output, dict):
        return False, "출력이 JSON 객체가 아님"
    if "next_action" not in output:
        return False, "next_action 필드 없음"
    if output["next_action"] not in ACTIONS:
        return False, f"허용되지 않은 행동: {output['next_action']}"
    if output["next_action"] in ("MOVE_TO", "OBSERVE") and not output.get("target"):
        return False, f"{output['next_action']}인데 target이 없음"
    if output["next_action"] == "RETURN_HOME" and output.get("target") != "HOME":
        return False, "RETURN_HOME의 target은 HOME이어야 함"
    if (
        allowed_waypoints
        and output["next_action"] in ("MOVE_TO", "RETURN_HOME")
        and output.get("target") not in allowed_waypoints
    ):
        return False, f"등록되지 않은 이동 목적지: {output.get('target')}"
    return True, "ok"
