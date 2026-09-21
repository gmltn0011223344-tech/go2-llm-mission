"""
Rule 기반 판단 — 안전장치와 대체 수단.

방향 (2026-09-21): Rule은 LLM과 성능을 겨루는 비교 대상이 아니라
1) ERROR·미등록 목적지처럼 LLM을 거치면 안 되는 상황의 안전 규칙,
2) LLM 호출·출력이 잘못됐을 때의 대체 판단
으로 사용한다. 출력 형식은 LLM과 같다(mode 포함).
"""


def _d(action, target, reason, mode="AUTO", question=None):
    return {"mode": mode, "next_action": action, "target": target,
            "question": question, "reason": reason, "source": "rule"}


def _ask(question, reason):
    return _d(None, None, reason, mode="ASK", question=question)


def rule_based_next_action(state, context, max_retry=1):
    """
    context: current_target, current_action, retry_count, remaining_tasks,
             (선택) registered=False, needs_alternative=True
    """
    target = context.get("current_target")
    retry = context.get("retry_count", 0)
    remaining = context.get("remaining_tasks", [])

    if state == "ERROR":
        return _d("STOP", None, "안전 규칙: 오류 발생 시 즉시 정지")
    if context.get("registered") is False:
        return _ask(f"'{target}'은(는) 등록되지 않은 목적지입니다. 등록된 목적지로 다시 지시해 주세요.",
                    "안전 규칙: 미등록 목적지로는 임의로 이동하지 않음")
    if state in ("REACHED", "TARGET_FOUND"):
        return continue_or_stop(remaining, "정상 진행, 다음 작업으로")

    first = retry < max_retry and not context.get("needs_alternative")

    if state in ("NO_PATH", "TIMEOUT"):
        if first:
            return _d("RETRY", target, f"{state} 첫 발생 → 같은 목적지로 1회 재시도")
        return _ask(f"{target}(으)로 이동하지 못했습니다. 다시 시도할까요, 복귀할까요, 정지할까요?",
                    "반복 실패 또는 대체 목적지 필요 → 임의 행동 대신 사용자 확인")

    if state == "TARGET_NOT_FOUND":
        if first:
            return _d("OBSERVE", target, "목표물 미발견 → 촬영 방향을 바꿔 1회 재탐색")
        return _ask(f"{target}을(를) 찾지 못했습니다. 다시 찾을까요, 복귀할까요, 정지할까요?",
                    "재탐색 후에도 미발견 → 사용자 확인")

    return _d("STOP", None, f"정의되지 않은 상태값({state}) → 안전 정지")


def continue_or_stop(remaining, reason):
    """다음 작업이 남아 있으면 그 작업, 없으면 정지(=임무 종료)."""
    if remaining:
        nxt = remaining[0]
        return _d(nxt["action"], nxt.get("target"), reason)
    return _d("STOP", None, "남은 작업 없음, 임무 종료")


_continue_or_stop = continue_or_stop   # 이전 이름 호환
