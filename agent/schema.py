"""
Go2 자연어 임무 시스템 - 행동/상태/판단 스키마

행동(Action)은 5개로 제한합니다. LLM이든 Rule이든 이 밖의 값을 내면
실행하지 않고 대체하거나 정지합니다.

판단 방식(mode)
- AUTO: 위험이 낮고 해결 방법이 명확 → 로봇이 스스로 다음 행동 수행
- ASK : 반복 실패·미등록 목적지·대체 목적지 필요 등 → 사용자 확인 전까지 실행하지 않음
"""

ACTIONS = [
    "MOVE_TO",      # target으로 이동
    "OBSERVE",      # 현재 위치에서 target 물체를 확인 (재촬영 포함)
    "RETRY",        # 방금 하던 작업을 한 번 더 시도
    "RETURN_HOME",  # 시작 지점으로 복귀
    "STOP",         # 안전 정지
]

STATES = [
    "REACHED",           # 목적지 도착
    "NO_PATH",           # 경로 이동 실패
    "TIMEOUT",           # 제한시간 초과
    "TARGET_FOUND",      # 목표물 발견
    "TARGET_NOT_FOUND",  # 목표물 미발견
    "ERROR",             # 오류
]

MODES = ["AUTO", "ASK"]

NORMAL_STATES = {"REACHED", "TARGET_FOUND"}          # 판단 호출 없이 계획대로 진행
FAILURE_STATES = {"NO_PATH", "TIMEOUT", "TARGET_NOT_FOUND"}

# 실제 좌표가 등록된 웨이포인트만 둔다. robot_executor.WAYPOINTS와 반드시 일치시킬 것.
# 좌표가 확정되지 않은 RED/BLUE/GREEN 등은 확정 전까지 넣지 않는다.
REGISTERED_WAYPOINTS = {"A", "B", "HOME"}

# YOLO 기본 클래스 중 시연에 쓰는 물체
ALLOWED_OBJECTS = {"BOTTLE", "BACKPACK", "CHAIR", "LAPTOP"}


def validate_action_output(output, allowed_waypoints=None, allowed_objects=None):
    """
    LLM/Rule이 내놓은 판단 JSON이 스키마를 지키는지 검사한다.
    mode가 없으면 AUTO로 본다(초기 작업 계획 검증과의 호환).
    """
    if not isinstance(output, dict):
        return False, "출력이 JSON 객체가 아님"
    mode = output.get("mode", "AUTO")
    if mode not in MODES:
        return False, f"알 수 없는 mode: {mode}"

    if mode == "ASK":
        if output.get("next_action") is not None:
            return False, "ASK는 사용자 승인 전 실행할 행동을 포함할 수 없음"
        question = output.get("question")
        if not isinstance(question, str) or not question.strip():
            return False, "ASK인데 사용자 질문이 없음"
        return True, "ok"

    action, target = output.get("next_action"), output.get("target")
    if action not in ACTIONS:
        return False, f"허용되지 않은 행동: {action}"
    if action in ("MOVE_TO", "OBSERVE") and not target:
        return False, f"{action}인데 target이 없음"
    if action == "RETURN_HOME" and target != "HOME":
        return False, "RETURN_HOME의 target은 HOME이어야 함"
    if allowed_waypoints and action in ("MOVE_TO", "RETURN_HOME") and target not in allowed_waypoints:
        return False, f"등록되지 않은 이동 목적지: {target}"
    if allowed_objects and action == "OBSERVE" and target not in allowed_objects:
        return False, f"허용되지 않은 탐색 대상: {target}"
    return True, "ok"
