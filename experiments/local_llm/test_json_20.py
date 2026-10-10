# -*- coding: utf-8 -*-
"""Run one fixed observation through qwen3.5:4b 20 times.

This checks JSON parsing and the expected output schema for the Ollama
Python integration. Each call sends the same messages with no chat history.
"""

import json
import time

from ollama import chat


MODEL = "qwen3.5:4b"
REPEATS = 20
PASS_THRESHOLD = 18  # 90% of 20

SITUATIONS = [
    "NORMAL",
    "OBSERVATION_ANOMALY",
    "POSSIBLE_REAL_CHANGE",
    "NAV_FAILURE",
]
ACTIONS = ["CONTINUE", "REOBSERVE", "CHANGE_VIEWPOINT", "RETRY_NAV"]

SCHEMA = {
    "type": "object",
    "properties": {
        "situation": {"type": "string", "enum": SITUATIONS},
        "action": {"type": "string", "enum": ACTIONS},
        "reason": {"type": "string"},
    },
    "required": ["situation", "action", "reason"],
}

SYSTEM = """해양생물 조사 판단 모델이다. starfish(불가사리)와 shell(조개)의 개체수 관측을 판단한다.

용어와 입력:
- 탐지 신뢰도 0.7 미만은 낮음, 0.7 이상은 높음이다.
- same_view_reobserve_count는 같은 시야에서 반복 관측한 횟수다.
- alternate_view_observations에는 B_SIDE처럼 다른 시야에서 실제로 얻은 관측만 들어간다.
  비어 있으면 다른 시야를 아직 확인하지 않은 것이다.
- 관측이 없으면 current_observation이 null이다.
- 입력에 없는 관측 결과를 있다고 가정하지 않는다.
- baseline_count와의 개체수 차이가 1 이하면 비슷함, 2 이상이면 큰 차이로 본다.

상황 기준:
- nav_state가 NAV_FAILURE이면 NAV_FAILURE.
- NORMAL: 현재 관측의 confidence가 0.7 이상이고 baseline_count와 차이가 1 이하이다.
- OBSERVATION_ANOMALY: confidence가 0.7 미만이거나 baseline_count와 차이가 2 이상이지만,
  다른 시야에서 고신뢰도로 같은 결과가 확인되지 않았다.
- POSSIBLE_REAL_CHANGE: 현재 시야와 다른 시야 모두 confidence가 0.7 이상이고,
  두 관측 모두 baseline_count와 2 이상 차이가 같은 방향으로 나타났다.
- 다른 시야에서 baseline_count에 가까운 값으로 회복되면 OBSERVATION_ANOMALY로 분류한다.

행동 기준:
- NAV_FAILURE이면 RETRY_NAV.
- NORMAL이면 CONTINUE.
- OBSERVATION_ANOMALY이고 same_view_reobserve_count가 0이면 REOBSERVE.
- OBSERVATION_ANOMALY이고 same_view_reobserve_count가 1 이상이며
  alternate_view_observations가 비어 있으면 CHANGE_VIEWPOINT.
- 다른 시야에서 baseline_count에 가까운 값으로 회복되었으면 CONTINUE.
- POSSIBLE_REAL_CHANGE이면 CONTINUE.

근거 작성:
- 입력에 실제로 들어 있는 수치와 관측만 언급한다.
- 다른 시야에서 확인되지 않았다면 "다른 시야에서 확인됐다"고 쓰지 않는다.
- NAV_FAILURE일 때는 confidence나 개체수를 근거로 쓰지 않는다.
- 한국어로 한 문장."""

# One representative input, intentionally identical on all 20 calls.
USER_INPUT = json.dumps(
    {
        "site": "B",
        "species": "starfish",
        "baseline_count": 8,
        "current_observation": {
            "viewpoint": "B_MAIN",
            "count": 3,
            "confidence": 0.4,
        },
        "same_view_reobserve_count": 0,
        "alternate_view_observations": [],
        "nav_state": "OK",
    },
    ensure_ascii=False,
    indent=2,
)


def validate_output(content):
    """Return (JSON parsed, schema valid, parsed value or None, error)."""
    try:
        value = json.loads(content)
    except (json.JSONDecodeError, TypeError) as exc:
        return False, False, None, f"JSON 파싱 실패: {exc}"

    if not isinstance(value, dict):
        return True, False, value, "최상위 값이 JSON 객체가 아님"
    if set(value) != {"situation", "action", "reason"}:
        return True, False, value, "필수 키가 다르거나 추가 키가 있음"
    if value["situation"] not in SITUATIONS:
        return True, False, value, "situation 값이 enum에 없음"
    if value["action"] not in ACTIONS:
        return True, False, value, "action 값이 enum에 없음"
    if not isinstance(value["reason"], str):
        return True, False, value, "reason이 문자열이 아님"
    return True, True, value, None


def main():
    parsed_count = 0
    schema_count = 0
    total_seconds = 0.0

    print(f"모델: {MODEL} / 같은 입력 반복: {REPEATS}회")
    print("측정: JSON 파싱 성공과 키·enum·자료형 검증")
    print("각 요청은 새 messages 목록으로 보내 대화 맥락을 공유하지 않습니다.\n")

    for i in range(1, REPEATS + 1):
        started = time.monotonic()
        try:
            kwargs = {
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": USER_INPUT},
                ],
                "format": SCHEMA,
                "options": {"temperature": 0},
                "think": False,
            }
            response = chat(**kwargs)
            content = response.message.content
            parsed, schema_ok, value, error = validate_output(content)
            parsed_count += int(parsed)
            schema_count += int(schema_ok)
            elapsed = time.monotonic() - started
            total_seconds += elapsed

            status = "파싱 O / 스키마 O" if schema_ok else (
                "파싱 O / 스키마 X" if parsed else "파싱 X / 스키마 X"
            )
            print(f"[{i:02d}/{REPEATS}] {status} ({elapsed:.1f}초)")
            if value is not None:
                print(
                    f"  situation={value.get('situation')!r}, "
                    f"action={value.get('action')!r}"
                )
            if error:
                print(f"  오류: {error}")
        except Exception as exc:
            elapsed = time.monotonic() - started
            total_seconds += elapsed
            print(f"[{i:02d}/{REPEATS}] 호출 실패 ({elapsed:.1f}초): {type(exc).__name__}: {exc}")

    parse_rate = parsed_count / REPEATS * 100
    schema_rate = schema_count / REPEATS * 100
    print("\n결과")
    print(f"JSON 파싱: {parsed_count}/{REPEATS} ({parse_rate:.0f}%)")
    print(f"스키마 검증: {schema_count}/{REPEATS} ({schema_rate:.0f}%)")
    print(f"평균 응답시간: {total_seconds / REPEATS:.1f}초")
    print(f"90% 기준: {'통과' if schema_count >= PASS_THRESHOLD else '미통과'} ({PASS_THRESHOLD}/{REPEATS} 이상 필요)")
    print("상황·행동 판단의 정답률은 이 형식 검사에 포함하지 않습니다.")


if __name__ == "__main__":
    main()
