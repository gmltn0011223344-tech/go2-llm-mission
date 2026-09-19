"""
Rule 기반 다음 행동 결정.

친구분이 준 표를 그대로 코드로 옮긴 것입니다. 상태값과 '지금까지 몇 번
재시도했는지'만 보고 기계적으로 답을 정합니다 — 상황을 '이해'하지 않습니다.
이게 바로 LLM 버전과 비교했을 때 한계가 드러나야 하는 지점입니다.
"""


def rule_based_next_action(state: str, context: dict) -> dict:
    """
    state: STATES 중 하나
    context: {
        "current_target": str,       # 지금 수행 중이던 목표 (예: "BLUE")
        "retry_count": int,          # 이 작업에서 이미 재시도한 횟수
        "remaining_tasks": list,     # 아직 안 한 작업들 (다음 작업 확인용)
    }
    반환: {"next_action": ..., "target": ..., "reason": ...}
    """
    target = context.get("current_target")
    retry = context.get("retry_count", 0)
    remaining = context.get("remaining_tasks", [])

    if state == "REACHED":
        return _continue_or_stop(remaining, "정상 도착, 다음 작업으로 진행")

    if state == "NO_PATH":
        if retry < 1:
            return {"next_action": "RETRY", "target": target,
                    "reason": "경로 없음 → 규칙상 1회 재시도"}
        return {"next_action": "STOP", "target": None,
                "reason": "재시도 후에도 경로 없음 → 규칙상 정지"}

    if state == "TIMEOUT":
        if retry < 1:
            return {"next_action": "RETRY", "target": target,
                    "reason": "시간 초과 → 규칙상 1회 재시도"}
        return {"next_action": "STOP", "target": None,
                "reason": "재시도 후에도 시간 초과 → 규칙상 정지"}

    if state == "TARGET_FOUND":
        return _continue_or_stop(remaining, "관찰 성공, 다음 작업으로 진행")

    if state == "TARGET_NOT_FOUND":
        return {"next_action": "RETURN_HOME", "target": "HOME",
                "reason": "목표물 없음 → 규칙상 재탐색 없이 복귀"}

    if state == "ERROR":
        return {"next_action": "STOP", "target": None,
                "reason": "오류 발생 → 규칙상 안전 정지"}

    return {"next_action": "STOP", "target": None,
            "reason": f"정의되지 않은 상태값({state}) → 안전하게 정지"}


def _continue_or_stop(remaining: list, reason: str) -> dict:
    """다음 작업이 남아있으면 그걸 실행, 없으면 정지(=임무 종료)."""
    if remaining:
        nxt = remaining[0]
        return {"next_action": nxt["action"], "target": nxt.get("target"),
                "reason": reason}
    return {"next_action": "STOP", "target": None,
            "reason": "남은 작업 없음, 임무 종료"}
