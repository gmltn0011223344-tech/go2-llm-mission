"""
agent/evaluation.py — AUTO/ASK 판단 정확도 평가용 정답표와 채점

실험 전에 시나리오별 정답을 미리 정해 둔다. STOP = 즉시 정지가 정답.
표본이 적으므로 비율보다 "8개 중 7개"처럼 실제 횟수로 기록한다.
"""

GOLD_SCENARIOS = [
    {"name": "시간초과 첫 발생", "state": "TIMEOUT",
     "ctx": {"current_action": "MOVE_TO", "current_target": "A", "retry_count": 0}, "expected": "AUTO"},
    {"name": "경로실패 첫 발생", "state": "NO_PATH",
     "ctx": {"current_action": "MOVE_TO", "current_target": "A", "retry_count": 0}, "expected": "AUTO"},
    {"name": "경로실패 반복", "state": "NO_PATH",
     "ctx": {"current_action": "MOVE_TO", "current_target": "A", "retry_count": 1}, "expected": "ASK"},
    {"name": "미발견·재촬영 가능", "state": "TARGET_NOT_FOUND",
     "ctx": {"current_action": "OBSERVE", "current_target": "BOTTLE", "retry_count": 0}, "expected": "AUTO"},
    {"name": "미발견 반복", "state": "TARGET_NOT_FOUND",
     "ctx": {"current_action": "OBSERVE", "current_target": "BOTTLE", "retry_count": 1}, "expected": "ASK"},
    {"name": "미등록 목적지", "state": "NO_PATH",
     "ctx": {"current_action": "MOVE_TO", "current_target": "C", "retry_count": 0, "registered": False}, "expected": "ASK"},
    {"name": "대체 목적지 필요", "state": "NO_PATH",
     "ctx": {"current_action": "MOVE_TO", "current_target": "B", "retry_count": 0, "needs_alternative": True}, "expected": "ASK"},
    {"name": "시스템 오류", "state": "ERROR",
     "ctx": {"current_action": "MOVE_TO", "current_target": "A", "retry_count": 0}, "expected": "STOP"},
]


def outcome(decision):
    if decision["mode"] == "AUTO" and decision["next_action"] == "STOP":
        return "STOP"
    return decision["mode"]


def score(pairs):
    """pairs: [(정답, 판단)] → 일치 수와 ASK 기준 Precision/Recall/F1"""
    tp = sum(e == "ASK" and p == "ASK" for e, p in pairs)
    fp = sum(e != "ASK" and p == "ASK" for e, p in pairs)
    fn = sum(e == "ASK" and p != "ASK" for e, p in pairs)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    correct = sum(e == p for e, p in pairs)
    return {"correct": correct, "total": len(pairs),
            "ask_precision": precision, "ask_recall": recall, "ask_f1": f1}
