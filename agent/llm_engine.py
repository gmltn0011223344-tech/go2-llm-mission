"""
LLM 기반 작업 분해 + 다음 행동 결정.

핵심 구조: real_* 함수는 실제 Anthropic API를 호출합니다 (ANTHROPIC_API_KEY
환경변수 필요). API 키가 없는 지금은 mock_* 함수가 대신 동작해서, "배관"이
제대로 연결되는지(입력→JSON 파싱→검증)를 먼저 확인할 수 있게 했습니다.

집에 가서 API 키만 설정하면(export ANTHROPIC_API_KEY=...) 아무 코드도
안 고치고 진짜 LLM 결과로 바로 바뀝니다 — llm_next_action()과
decompose_command()가 자동으로 real_* 쪽을 씁니다.
"""

import os
import json
from agent.schema import ACTIONS

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
        "next_action": {"type": "string", "enum": ACTIONS},
        "target": {"type": ["string", "null"]},
        "reason": {"type": "string"},
    },
    "required": ["next_action", "target", "reason"],
    "additionalProperties": False,
}

DECOMPOSE_SYSTEM = f"""당신은 4족보행 로봇 Go2의 작업 계획기입니다.
사용자의 자연어 명령을 아래 행동만 사용한 순서 있는 작업 목록(JSON)으로 변환하세요.

사용 가능한 행동: {ACTIONS}
- MOVE_TO는 target에 장소 이름(예: RED, BLUE)을 넣으세요.
- OBSERVE는 target에 찾을 물체 이름(예: LAPTOP)을 넣으세요.

다른 설명 없이 아래 형식의 JSON만 출력하세요.
{{"tasks": [{{"action": "...", "target": "..."}}, ...]}}
"""

NEXT_ACTION_SYSTEM = f"""당신은 4족보행 로봇 Go2의 예외 상황 대응 판단기입니다.
현재 상태값과 상황을 보고 다음 행동을 결정하세요.

사용 가능한 행동: {ACTIONS}
상태값 의미: REACHED(도착) / NO_PATH(경로없음) / TIMEOUT(시간초과) /
TARGET_FOUND(물체발견) / TARGET_NOT_FOUND(물체못찾음) / ERROR(오류)

단순 규칙(예: 무조건 1회 재시도 후 정지)과 달리, 재시도 횟수·남은 작업·
목표를 함께 고려해 더 합리적인 대안을 제시하세요. 예를 들어 NO_PATH이면
같은 경로를 반복 시도하기보다 다른 목표나 방향을 고려할 수 있고,
TARGET_NOT_FOUND이면 즉시 복귀하기보다 한 번 더 다른 위치에서 관찰을
시도하는 편이 나을 수 있습니다. 다만 재시도가 이미 있었다면 안전하게
정지하거나 복귀하세요.

다른 설명 없이 아래 형식의 JSON만 출력하세요.
{{"next_action": "...", "target": "..." 또는 null, "reason": "..."}}
"""


# ---------------------------------------------------------------- real calls
def _client():
    import anthropic
    return anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수를 자동으로 읽습니다.


def real_decompose_command(nl_command: str) -> dict:
    resp = _client().messages.create(
        model=MODEL_NAME, max_tokens=500, system=DECOMPOSE_SYSTEM,
        messages=[{"role": "user", "content": nl_command}],
        output_config={"format": {"type": "json_schema", "schema": PLAN_SCHEMA}},
    )
    return json.loads(resp.content[0].text)


def real_llm_next_action(state: str, context: dict) -> dict:
    user_msg = f"상태값: {state}\n상황: {json.dumps(context, ensure_ascii=False)}"
    resp = _client().messages.create(
        model=MODEL_NAME, max_tokens=300, system=NEXT_ACTION_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
        output_config={"format": {"type": "json_schema", "schema": DECISION_SCHEMA}},
    )
    return json.loads(resp.content[0].text)


# ---------------------------------------------------------------- mock calls
# API 키 없이 파이프라인(입출력 형식)만 먼저 검증하기 위한 더미 로직입니다.
# 진짜 LLM 판단이 아니므로 발표·보고서에 결과로 쓰면 안 됩니다.
def mock_decompose_command(nl_command: str) -> dict:
    tasks = []
    if "빨간" in nl_command or "RED" in nl_command.upper():
        tasks.append({"action": "MOVE_TO", "target": "RED"})
    if "파란" in nl_command or "BLUE" in nl_command.upper():
        tasks.append({"action": "MOVE_TO", "target": "BLUE"})
    if "노트북" in nl_command:
        tasks.append({"action": "OBSERVE", "target": "LAPTOP"})
    if "돌아" in nl_command or "복귀" in nl_command:
        tasks.append({"action": "RETURN_HOME", "target": "HOME"})
    return {"tasks": tasks}


def mock_llm_next_action(state: str, context: dict) -> dict:
    from agent.rule_engine import _continue_or_stop
    target = context.get("current_target")
    retry = context.get("retry_count", 0)
    remaining = context.get("remaining_tasks", [])

    if state == "REACHED":
        return _continue_or_stop(remaining, "(MOCK) 정상 도착, 다음 작업 진행")
    if state == "TARGET_FOUND":
        return _continue_or_stop(remaining, "(MOCK) 관찰 성공, 다음 작업 진행")
    if state == "NO_PATH" and retry < 1:
        return {"next_action": "MOVE_TO", "target": f"{target}_ALT",
                "reason": "(MOCK) 기존 경로 대신 인접한 대안 경로로 우회 시도"}
    if state == "TIMEOUT" and retry < 1:
        return {"next_action": "RETRY", "target": target,
                "reason": "(MOCK) 일시적 지연일 수 있어 1회 재시도"}
    if state == "TARGET_NOT_FOUND" and retry < 1:
        return {"next_action": "OBSERVE", "target": target,
                "reason": "(MOCK) 다른 각도에서 한 번 더 관찰 후 그래도 없으면 복귀"}
    if state == "ERROR":
        return {"next_action": "STOP", "target": None,
                "reason": "(MOCK) 오류 상황은 규칙과 동일하게 안전 정지"}
    return {"next_action": "RETURN_HOME", "target": "HOME",
            "reason": "(MOCK) 추가 시도 실패, 복귀"}


# ---------------------------------------------------------------- entrypoint
def decompose_command(nl_command: str) -> dict:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return real_decompose_command(nl_command)
    print("[안내] ANTHROPIC_API_KEY가 없어 mock으로 대체합니다.")
    return mock_decompose_command(nl_command)


def llm_next_action(state: str, context: dict) -> dict:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return real_llm_next_action(state, context)
    print("[안내] ANTHROPIC_API_KEY가 없어 mock으로 대체합니다.")
    return mock_llm_next_action(state, context)
