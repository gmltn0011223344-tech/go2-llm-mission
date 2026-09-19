"""
agent/state_adapter.py

다령 님의 navigation.py가 내는 실제 상태 이름을, 우리 LLM/Rule 모듈이
쓰는 6개 표준 상태로 변환하는 '번역기'입니다.

왜 필요한가:
- navigation.py는 GOAL_REACHED / PATH_BLOCKED / GOAL_OCCUPIED / NAV_FAILURE /
  NAV_TIMEOUT 같은 자기만의 이름을 씁니다.
- 우리 rule_engine / llm_engine은 REACHED / NO_PATH / TIMEOUT /
  TARGET_FOUND / TARGET_NOT_FOUND / ERROR 6개만 압니다.
- 이 파일 하나만 고치면 다령 님이 상태 이름을 바꿔도 나머지 코드는 안 건드려도 됩니다.
  (= 연결 지점을 한 곳에 모아두는 것)
"""

# 다령 님 navigation.state 값  ->  우리 표준 상태
NAV_STATE_MAP = {
    "GOAL_REACHED": "REACHED",
    "PATH_BLOCKED": "NO_PATH",      # navigation.py의 NO_PATH 로그에서 설정됨
    "GOAL_OCCUPIED": "NO_PATH",     # 목적지가 막힘 → 경로 없음과 동일 취급
    "NAV_FAILURE": "ERROR",
    "NAV_TIMEOUT": "TIMEOUT",
    "ABNORMAL": "ERROR",
    "IDLE": "ERROR",               # 예기치 못한 상태
}


def nav_result_to_state(success: bool, nav_state: str) -> str:
    """
    navigation.goto_and_wait()의 반환값(success)과 navigation.state를 받아
    우리 표준 상태 문자열로 변환.

    - 도착 성공이면 무조건 REACHED
    - 실패면 navigation.state를 위 표에서 찾아 매핑, 없으면 ERROR
    """
    if success:
        return "REACHED"
    return NAV_STATE_MAP.get(nav_state, "ERROR")


def observe_result_to_state(found: bool) -> str:
    """
    Vision의 관찰 결과(found: True/False)를 표준 상태로 변환.
    (Vision 모듈은 vision/detector.py에서 담당)
    """
    return "TARGET_FOUND" if found else "TARGET_NOT_FOUND"
