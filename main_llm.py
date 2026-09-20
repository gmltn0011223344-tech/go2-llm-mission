"""
main_llm.py  (프로젝트 루트에서 실행)

다령 님의 로봇 연결/맵/위치추정 코드를 그대로 쓰고, 그 위에 LLM 기반
자연어 임무 수행 + 예외 대응 루프를 얹은 실제 로봇용 진입점입니다.

다령 님 원본 main.py는 건드리지 않았습니다. (A→B 하드코딩 데모 그대로 보존)
이 파일은 그와 별개로 동작하며, 자연어 명령을 받아 실행합니다.

실행 전:
    export GO2_AES_KEY="..."          # 다령 님 README 참고
    export ANTHROPIC_API_KEY="..."    # 내 LLM 사용 (없으면 mock으로 동작)
    python3 main_llm.py

주의:
- RobotExecutor와 MissionRunner를 모두 async로 통일했습니다.
- 실제 로봇과 카메라 통합 실행은 아직 검증 전입니다.
"""

import asyncio

from robot.connection import Go2Connection
from robot.navigation import Go2Navigation
from robot.localization import Go2Localization
from robot.map_manager import Go2MapManager

from agent.robot_executor import RobotExecutor
from agent.mission_runner import MissionRunner


MAP_ID = "9slQWWk1gZduAEWnEpiUyg"
INITIAL_POSE = (0.013, 0.023, 0.000)

# 시연 명령 (자연어)
COMMAND = "빨간 지점을 지나 파란 지점에서 노트북이 있는지 확인하고 돌아와"

# 예외 대응을 Rule로 할지 LLM으로 할지 ("rule" / "llm")
DECISION_MODE = "llm"


async def setup_robot():
    """다령 님 main.py의 연결~localization 절차를 그대로 재사용."""
    robot = Go2Connection()
    conn = await robot.connect()

    navigation = Go2Navigation(conn)
    navigation.subscribe_server_log()

    localization = Go2Localization(conn)
    localization.subscribe_pose()

    map_manager = Go2MapManager(conn)
    print("[SYSTEM] Go2 system ready.")

    await map_manager.activate_map(MAP_ID)

    navigation.reset_localization_event()
    localization.set_initial_pose(*INITIAL_POSE)
    await asyncio.sleep(0.1)

    localization.start()
    ready = await navigation.wait_for_localization(timeout=60.0)
    if not ready:
        raise RuntimeError("Localization 실패 — 임무를 시작할 수 없습니다.")

    await asyncio.sleep(0.5)
    print("[CURRENT POSE]", localization.get_pose())
    return navigation, localization


async def main():
    navigation, localization = await setup_robot()

    # 실제 실행부 구성 (카메라는 아직 없으므로 vision은 mock으로 동작)
    executor = RobotExecutor(navigation, localization, camera=None)

    print("\n==============================")
    print(f"[MISSION] 명령: {COMMAND}")
    print(f"[MISSION] 예외 대응 방식: {DECISION_MODE}")
    print("==============================\n")

    runner = MissionRunner(executor, decision_mode=DECISION_MODE)
    result = await runner.run(COMMAND)

    print("\n==============================")
    print("[MISSION] 종료")
    print(f"  종료 상태: {result['status']}, 성공 여부: {result['success']}, 총 스텝: {result['steps']}")
    print("==============================")
    for e in result["log"]:
        print(f"  {e['step']}. 실행={e['executed']['action']}:"
              f"{e['executed'].get('target')} 상태={e['state']} → "
              f"결정={e['next_action']}:{e.get('next_target')} | {e['reason']}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[SYSTEM] Program stopped.")
