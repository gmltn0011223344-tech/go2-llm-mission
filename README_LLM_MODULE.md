# LLM 임무 계획 · 예외 대응 모듈 

다령 님의 로봇 실행부(`robot/`, `main.py`) 위에 사용하는 **자연어 임무 계획 + 예외 대응** 모듈입니다.


## 방향 (2026-09-21 팀 회의)
- 핵심은 Rule vs LLM 성능 비교가 아니라, **예외 발생 시 LLM이 AUTO(스스로 대응)와 ASK(사용자 확인)를 적절히 선택**하는 것입니다.
- Rule은 경쟁 방식이 아니라 **안전장치와 LLM 오류 시 대체 수단**입니다.

## 전체 흐름
```
자연어 명령 → LLM 작업 분해 → Go2 실행 → 상태 수신
   ├ REACHED / TARGET_FOUND → 계획대로 다음 작업
   └ 예외 상태 → 안전 규칙 → LLM 판단(AUTO/ASK) → 출력 검증 → (실패 시 Rule 대체)
                   AUTO → 실행   /   ASK → 사용자 답변 후 실행
```

## 판단 결과 형식 (`agent/schema.py`, `agent/llm_engine.py`)
```json
{"mode": "AUTO", "next_action": "RETRY", "target": "A", "question": null, "reason": "첫 경로 실패, 1회 재시도"}
{"mode": "ASK",  "next_action": null,    "target": null, "question": "A로 이동하지 못했습니다. 다시 시도할까요, 복귀할까요?", "reason": "반복 실패"}
```

## 안전 규칙
- 등록되지 않은 웨이포인트 이동 금지 (`schema.REGISTERED_WAYPOINTS` = A, B, HOME. `robot_executor.WAYPOINTS`와 불일치 시 실행 중단)
- 미등록 목적지가 들어간 명령은 실행하지 않고 ASK_PENDING으로 종료
- 허용되지 않은 행동 실행 금지 (`MOVE_TO`, `OBSERVE`, `RETRY`, `RETURN_HOME`, `STOP`)
- `ERROR`는 LLM을 거치지 않고 즉시 정지
- 같은 작업의 자동 재시도는 1회까지, 초과 시 ASK
- LLM JSON 파싱·검증 실패 시 Rule 대체
- ASK는 사용자 답변 전 실행 금지

## AUTO/ASK 정답표
| 상황 | 정답 |
|---|---|
| 시간 초과·경로 실패 첫 발생 | AUTO |
| 목표물 미발견이지만 재촬영 가능 | AUTO |
| 경로 실패·미발견 반복 | ASK |
| 미등록 목적지 / 사용자가 지정하지 않은 대체 목적지 필요 | ASK |
| 시스템 오류 | 즉시 정지 |

## 실행
```
python3 -m unittest tests.test_auto_ask   # 테스트 9개
python3 run_auto_ask_eval.py             # AUTO/ASK 판단 평가 (API 키 없으면 mock → 점검용, LLM 성능 아님)
python3 run_auto_ask_eval.py --rule      # Rule 대체 정책만으로 평가
python3 main_llm.py                      # 실제 로봇 (통합 전 검증 필요, ASK는 터미널에서 답변)
```
종료 상태: MISSION_COMPLETED / SAFE_RETURN / STOPPED / ASK_PENDING(사용자 답변 대기) / FAILED
`run_comparison.py`(Rule vs mock 비교)는 참고용으로만 남겨 둡니다.

## 모듈
| 파일 | 역할 |
|---|---|
| schema.py | 행동 5종·상태 6종·mode, 등록 웨이포인트·물체, 출력 검증 |
| llm_engine.py | 작업 분해, AUTO/ASK 판단 (API 키 없으면 mock) |
| rule_engine.py | 안전 규칙 + LLM 오류 시 대체 판단 |
| mission_runner.py | 임무 루프, 판단 순서, ASK 처리 |
| evaluation.py | AUTO/ASK 정답표와 채점 |
| state_adapter.py | 다령 님 상태 이름 → 표준 상태 |
| robot_executor.py / sim_executor.py | 실제 Go2 / 시뮬레이터 실행부 |

## 확인된 것 / 아직 검증 전
- 확인: 상태·행동 형식, 작업 분해 mock, 비동기 MissionRunner, Navigation 상태 어댑터, AUTO/ASK 판단·안전 규칙·사용자 답변 처리 단위 테스트 9개
- 검증 전: 실제 Anthropic API 호출과 구조화 출력, 실제 사용자와의 질문·응답, Go2 Navigation·YOLO 통합, 전체 임무 실행, 실제 상황에서의 AUTO/ASK 판단 평가
