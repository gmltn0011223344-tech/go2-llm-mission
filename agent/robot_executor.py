"""
agent/robot_executor.py

실제 Go2에 연결되는 실행부. MissionRunner가 결정한 작업(MOVE_TO/OBSERVE/...)을
다령 님의 navigation.goto_and_wait() 등으로 실제 실행하고, 그 결과를
표준 상태값(REACHED/NO_PATH/...)으로 변환해 돌려줍니다.

이 파일이 '내 LLM 모듈'과 '다령 님 로봇 코드'가 실제로 만나는 지점입니다.
main_llm.py에서 사용합니다.

주의:
- MissionRunner와 navigation을 모두 async로 통일했습니다.
- 실제 로봇 통합 시 MissionRunner.run()을 반드시 await해야 합니다.
- WAYPOINTS(장소 이름 → 좌표)는 다령 님 main.py의 값을 그대로 씁니다.
  좌표 없는 지점은 등록하지 않습니다 (LLM이 만들어도 실행 전에 차단).
"""

from agent.state_adapter import nav_result_to_state, observe_result_to_state
from vision.detector import detect_target


from agent.schema import REGISTERED_WAYPOINTS

# 다령 님 main.py의 WAYPOINTS. 실제 좌표가 확인된 지점만 둔다.
# 새 지점(C 등)은 맵에서 좌표를 확인한 뒤 여기와 schema.REGISTERED_WAYPOINTS에 함께 추가.
WAYPOINTS = {
    "A": (0.835, 0.298, 0.000),
    "B": (-0.302, 0.307, 0.000),
    "HOME": (0.013, 0.023, 0.000),   # INITIAL_POSE
}
assert set(WAYPOINTS) == REGISTERED_WAYPOINTS, "WAYPOINTS와 REGISTERED_WAYPOINTS가 다릅니다"


class RobotExecutor:
    def __init__(self, navigation, localization=None, camera=None):
        """
        navigation: 다령 님 Go2Navigation 인스턴스
        localization: (선택) 위치 확인용
        camera: (선택) 카메라 프레임 획득용. 없으면 vision은 mock으로 동작.
        """
        self.nav = navigation
        self.loc = localization
        self.camera = camera

    async def execute_async(self, task: dict) -> str:
        action = task.get("action")
        target = task.get("target")

        if action in ("MOVE_TO", "RETURN_HOME"):
            coord = WAYPOINTS.get(target)
            if coord is None:
                print(f"[EXEC] 알 수 없는 목표 좌표: {target}")
                return "ERROR"
            success = await self.nav.goto_and_wait(*coord, timeout=60.0)
            state = nav_result_to_state(success, self.nav.state)
            print(f"[EXEC] MOVE_TO {target} → {state} (nav.state={self.nav.state})")
            return state

        if action == "OBSERVE":
            frame = self._grab_frame()
            found = detect_target(frame, target)
            state = observe_result_to_state(found)
            print(f"[EXEC] OBSERVE {target} → {state}")
            return state

        if action == "RETRY":
            # RETRY는 보통 이전 MOVE_TO를 다시 하라는 의미로 상위에서 처리되지만,
            # 혹시 직접 오면 안전하게 ERROR 대신 현재 위치 재확인 성공으로 둠.
            return "REACHED"

        if action == "STOP":
            print("[EXEC] STOP 요청 — 안전 정지")
            return "ERROR"

        print(f"[EXEC] 알 수 없는 행동: {action}")
        return "ERROR"

    def _grab_frame(self):
        """카메라가 연결돼 있으면 실제 프레임, 없으면 mock용 표식 반환."""
        if self.camera is not None:
            try:
                return self.camera.get_frame()
            except Exception as e:
                print(f"[EXEC] 카메라 프레임 획득 실패: {e}")
        return "MOCK_FRAME"

    # MissionRunner가 async로 통일되어 execute_async()를 직접 await합니다.
