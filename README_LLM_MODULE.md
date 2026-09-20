# LLM 임무 계획 · 예외 대응 모듈 (희수 담당분)

다령 님의 로봇 실행부(`robot/`, `main.py`) 위에 얹는 **자연어 임무 계획 +
예외 상황 대응** 모듈입니다. 다령 님 원본 파일은 하나도 수정하지 않았고,
`agent/`, `vision/`, `main_llm.py`, `run_comparison.py`만 새로 추가했습니다.

## 전체 흐름

```
자연어 명령
   ↓  decompose_command()        (agent/llm_engine.py)
작업 목록 JSON  [{MOVE_TO:RED}, {MOVE_TO:BLUE}, {OBSERVE:LAPTOP}, {RETURN_HOME}]
   ↓  await MissionRunner.run()  (agent/mission_runner.py)
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
API 키가 없을 때의 결과는 **Rule과 mock 적응형 판단의 코드 흐름 확인용**입니다.
실제 LLM 성능 자료로 사용하면 안 됩니다. 현재 mock에서는 물체없음 시나리오에서
Rule은 즉시 복귀하고 mock 판단은 1회 재관찰하여 판단 경로가 달라집니다.

실제 로봇 (다령 님 실행부와 연결):
```
export GO2_AES_KEY="..."          # 다령 님 README 참고
export ANTHROPIC_API_KEY="..."    # 없으면 mock으로 동작
export ANTHROPIC_MODEL="claude-sonnet-5"  # 생략 시 이 값 사용
python3 main_llm.py
```

## 아직 mock인 부분 (실제 붙일 때 바꿀 곳)

| 부분 | 현재 | 실제 연결 방법 |
|---|---|---|
| LLM 호출 | API 키 없으면 mock | `export ANTHROPIC_API_KEY` 설정 (코드 수정 불필요) |
| Vision 탐지 | `vision/detector.py`의 mock | `USE_REAL_VISION=True` + `real_detect_target()` 구현 |
| 스티커 좌표 | A/B 좌표 재사용 | `robot_executor.py`의 `WAYPOINTS` 실제 좌표 입력 |
| 모델명 | 기본값 `claude-sonnet-5` | 필요하면 `ANTHROPIC_MODEL` 환경변수로 변경 |

## 실제 통합 전에 남은 작업

- 다령 님 저장소에서 브랜치를 만든 뒤 이 모듈을 병합하고 실제 Go2로 실행
- 다령 님 `vision.py`가 탐지 결과를 반환하도록 바꿔 `OBSERVE`와 연결
- 실제 waypoint 좌표 확정 및 허용 목록 고정
- API 호출 성공, 구조화 출력, 호출 지연시간과 비용 기록
- AUTO/ASK 모드와 사용자 승인·거절·수정 처리 구현
- 실제 예외상황을 반복해 Rule과 LLM의 완료율·안전정지율·응답시간 비교
```
