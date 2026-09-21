"""
LLM 기반 작업 분해 + 예외 상황 판단(AUTO/ASK).

real_* 함수는 실제 Anthropic API를 호출합니다 (ANTHROPIC_API_KEY 필요).
키가 없으면 mock_* 함수가 대신 동작해 입출력 형식만 확인합니다.
mock 결과는 LLM 판단이 아니므로 발표·보고서에 결과로 쓰면 안 됩니다.

LLM의 역할: 현재 상태와 남은 임무를 보고
- AUTO: 스스로 처리할 다음 행동을 고르거나
- ASK : 사용자에게 확인할 질문을 만든다.
출력은 실행 전에 mission_runner에서 검증하며, 잘못되면 Rule로 대체합니다.
"""

import os
import json
from agent.schema import ACTIONS, MODES

MODEL_NAME = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ACTIONS},
                    "target": {"type": ["string", "null"]},
                },
                "required": ["action", "target"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["tasks"],
    "additionalProperties": False,
}

DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "enum": MODES},
        "next_action": {"anyOf": [{"type": "string", "enum": ACTIONS}, {"type": "null"}]},
        "target": {"type": ["string", "null"]},
        "question": {"type": ["string", "null"]},
        "reason": {"type": "string"},
    },
    "required": ["mode", "next_action", "target", "question", "reason"],
    "additionalProperties": False,
}

DECOMPOSE_SYSTEM = f"""당신은 4족보행 로봇 Go2의 작업 계획기입니다.
사용자의 자연어 명령을 아래 행동만 사용한 순서 있는 작업 목록(JSON)으로 변환하세요.

사용 가능한 행동: {ACTIONS}
- MOVE_TO는 target에 장소 이름(예: A, B)을 넣으세요.
- OBSERVE는 target에 찾을 물체 이름을 영문 대문자로 넣으세요(예: BOTTLE).
- 돌아오라는 말이 있으면 마지막에 RETURN_HOME(target: HOME)을 넣으세요.
- 명령에 없는 장소나 물체를 지어내지 마세요.

다른 설명 없이 아래 형식의 JSON만 출력하세요.
{{"tasks": [{{"action": "...", "target": "..."}}, ...]}}
"""

NEXT_ACTION_SYSTEM = f"""당신은 4족보행 로봇 Go2의 예외 상황 판단 모듈입니다.
로봇이 보낸 상태값과 남은 임무를 보고, 스스로 처리할지(AUTO) 사용자에게 확인할지(ASK) 결정하세요.

상태값: NO_PATH(경로 이동 실패) / TIMEOUT(제한시간 초과) / TARGET_NOT_FOUND(목표물 미발견)
사용 가능한 행동: {ACTIONS}

판단 기준
- AUTO: 위험이 낮고 해결 방법이 명확할 때만. 예) 첫 번째 경로 실패·시간 초과 → RETRY,
  첫 번째 미발견 → 같은 물체로 OBSERVE(방향을 바꿔 재촬영).
- ASK: 같은 작업이 이미 재시도됐을 때(retry_count >= max_retry), 사용자가 지정하지 않은
  대체 목적지가 필요할 때, 판단이 불확실하거나 안전이 걱정될 때.
  ASK이면 next_action과 target은 null, question에 사용자에게 보낼 한 문장을 쓰세요.
- 목적지는 allowed_waypoints, 물체는 allowed_objects 안에서만 고르세요.
  목록에 없는 좌표·목적지·행동은 절대 만들지 마세요.

다른 설명 없이 JSON만 출력하세요.
{{"mode": "AUTO" 또는 "ASK", "next_action": 행동 또는 null, "target": 값 또는 null,
  "question": 문장 또는 null, "reason": "판단 근거"}}
"""


# ---------------------------------------------------------------- real calls
def _client():
    import anthropic
    return anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수를 자동으로 읽습니다.


def real_decompose_command(nl_command):
    resp = _client().messages.create(
        model=MODEL_NAME, max_tokens=500, system=DECOMPOSE_SYSTEM,
        messages=[{"role": "user", "content": nl_command}],
        output_config={"format": {"type": "json_schema", "schema": PLAN_SCHEMA}},
    )
    return json.loads(resp.content[0].text)


def real_llm_next_action(state, context):
    user_msg = f"상태값: {state}\n상황: {json.dumps(context, ensure_ascii=False)}"
    resp = _client().messages.create(
        model=MODEL_NAME, max_tokens=400, system=NEXT_ACTION_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
        output_config={"format": {"type": "json_schema", "schema": DECISION_SCHEMA}},
    )
    decision = json.loads(resp.content[0].text)
    decision["source"] = "llm"
    return decision


# ---------------------------------------------------------------- mock calls
def mock_decompose_command(nl_command):
    cmd = nl_command.upper()
    tasks = []
    for words, place in ((("빨간", "RED"), "RED"), (("파란", "BLUE"), "BLUE"),
                         (("A 지점", "A지점"), "A"), (("B 지점", "B지점"), "B")):
        if any(w.upper() in cmd for w in words):
            tasks.append({"action": "MOVE_TO", "target": place})
    for words, obj in ((("노트북", "LAPTOP"), "LAPTOP"), (("병", "BOTTLE"), "BOTTLE"),
                       (("가방", "BACKPACK"), "BACKPACK"), (("의자", "CHAIR"), "CHAIR")):
        if any(w.upper() in cmd for w in words):
            tasks.append({"action": "OBSERVE", "target": obj})
    if "돌아" in nl_command or "복귀" in nl_command:
        tasks.append({"action": "RETURN_HOME", "target": "HOME"})
    return {"tasks": tasks}


def mock_llm_next_action(state, context):
    """API 없이 형식만 확인하는 더미 판단. Rule 대체 정책과 같은 결과를 낸다."""
    from agent.rule_engine import rule_based_next_action
    d = rule_based_next_action(state, context, context.get("max_retry", 1))
    d["reason"] = "(MOCK) " + d["reason"]
    d["source"] = "mock"
    return d


# ---------------------------------------------------------------- entrypoint
_notified = False


def _use_real():
    global _notified
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    if not _notified:
        print("[안내] ANTHROPIC_API_KEY가 없어 mock으로 대체합니다.")
        _notified = True
    return False


def decompose_command(nl_command):
    return real_decompose_command(nl_command) if _use_real() else mock_decompose_command(nl_command)


def llm_next_action(state, context):
    return real_llm_next_action(state, context) if _use_real() else mock_llm_next_action(state, context)
