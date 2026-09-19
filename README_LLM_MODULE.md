# LLM 임무 계획 · 예외 대응 모듈 (희수 담당분)

다령 님의 로봇 실행부(`robot/`, `main.py`) 위에 얹는 **자연어 임무 계획 +
예외 상황 대응** 모듈입니다. 다령 님 원본 파일은 하나도 수정하지 않았고,
`agent/`, `vision/`, `main_llm.py`, `run_comparison.py`만 새로 추가했습니다.

## 전체 흐름

```
자연어 명령
   ↓  decompose_command()        (agent/llm_engine.py)
작업 목록 JSON  [{MOVE_TO:RED}, {MOVE_TO:BLUE}, {OBSERVE:LAPTOP}, {RETURN_HOME}]
   ↓  MissionRunner.run()        (agent/mission_runner.py)
작업 하나 실행 → 상태값 수신 ── executor가 담당
   │                              · 실제 로봇: agent/robot_executor.py
   │                              · 시뮬레이터: agent/sim_executor.py
   ↓  상태값(REACHED/NO_PATH/...) 
다음 행동 결정  ── rule_based_next_action()  또는  llm_next_action()
   ↓
행동을 큐에 반영하고 반복
```

## 다령 님 코드와 만나는 지점

- **`agent/state_adapter.py`** — 이 파일이 두 코드를 잇는 다리입니다.
  다령 님 `navigation.state`(`GOAL_REACHED`, `PATH_BLOCKED`, `GOAL_OCCUPIED`,
  `NAV_FAILURE`, `NAV_TIMEOUT` 등)를 우리 표준 상태 6개
  (`REACHED`, `NO_PATH`, `TIMEOUT`, `TARGET_FOUND`, `TARGET_NOT_FOUND`, `ERROR`)로
  변환합니다. **상태 이름이 바뀌면 이 파일의 `NAV_STATE_MAP`만 고치면 됩니다.**
- **`agent/robot_executor.py`** — `navigation.goto_and_wait()`를 실제 호출하고
  결과를 표준 상태로 바꿔 돌려줍니다. `WAYPOINTS`의 RED/BLUE/GREEN 좌표만
  실제 스티커 위치로 채우면 됩니다.

## 행동 5종 · 상태 6종 (agent/schema.py)

- 행동: `MOVE_TO`, `OBSERVE`, `RETRY`, `RETURN_HOME`, `STOP`
- 상태: `REACHED`, `NO_PATH`, `TIMEOUT`, `TARGET_FOUND`, `TARGET_NOT_FOUND`, `ERROR`
- `validate_action_output()`으로 LLM이 스키마 밖 값을 내면 걸러냅니다.

## 실행 방법

로봇 없이 (발표 근거용 비교 실험):
```
python3 run_comparison.py
```
→ 4개 시나리오에서 Rule vs LLM 판단을 비교, `comparison_result.csv` 저장.
현재 결과: **경로차단·물체없음 2개 시나리오에서 LLM이 Rule과 다르게 대응**
(경로차단 시 Rule은 같은 경로 재시도, LLM은 대안 경로 우회 /
물체없음 시 Rule은 즉시 복귀, LLM은 다른 각도에서 재관찰).

실제 로봇 (다령 님 실행부와 연결):
```
export GO2_AES_KEY="..."          # 다령 님 README 참고
export ANTHROPIC_API_KEY="..."    # 없으면 mock으로 동작
python3 main_llm.py
```

## 아직 mock인 부분 (실제 붙일 때 바꿀 곳)

| 부분 | 현재 | 실제 연결 방법 |
|---|---|---|
| LLM 호출 | API 키 없으면 mock | `export ANTHROPIC_API_KEY` 설정 (코드 수정 불필요) |
| Vision 탐지 | `vision/detector.py`의 mock | `USE_REAL_VISION=True` + `real_detect_target()` 구현 |
| 스티커 좌표 | A/B 좌표 재사용 | `robot_executor.py`의 `WAYPOINTS` 실제 좌표 입력 |
| 모델명 | `agent/llm_engine.py`의 `MODEL_NAME` | Anthropic 콘솔에서 현재 사용 가능한 모델명 확인 후 교체 |
```
