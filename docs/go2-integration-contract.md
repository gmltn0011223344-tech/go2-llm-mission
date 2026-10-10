# Go2 팀원 실행부 호환성 점검 (2026-10-10)

> **범위:** 본인 저장소에 추가한 표준 라이브러리만 사용하는 순수 데이터 계약(Contract) 코드. 로봇 제어, DB 변경, 외부 저장소 수정 없음.

## 기준으로 읽은 외부 코드 (읽기 전용)

- [팀원 `memory/observation_memory.py`](https://github.com/daryung/go2_capstone/blob/main/memory/observation_memory.py): `save_observation(point_id, robot_x, robot_y, robot_yaw, navigation_state, starfish_count, starfish_confidence, shell_count, shell_confidence)`
- [팀원 `reciver.py`](https://github.com/daryung/go2_capstone/blob/main/reciver.py): `request_id`, `type`, `observation_ids`를 읽고 `decision.json`에 `{"request_id": ..., "status": "ok", "decision": {...}}` 반환
- [팀원 `agent/local_llm.py`](https://github.com/daryung/go2_capstone/blob/main/agent/local_llm.py): `decide(mission_observations)`; 상황·행동·대상·근거의 구조화 출력
- [팀원 `test_scenario1.py`](https://github.com/daryung/go2_capstone/blob/main/test_scenario1.py): 3개 지점 2회 순회(6개 observation ID), 재관측 시 1개 추가(7개)
- [본인 `vision/mbo_detector.py`](../vision/mbo_detector.py): `to_observation()`은 DB용 4개 필드 반환

## 이번에 추가한 것

`integration/go2_contract.py`의 세 함수:

1. `prepare_db_fields(point_id, pose, navigation_state, observation)`: `to_observation()` 결과와 로봇 pose를 묶어 팀원 DB 함수 인수와 같은 9개 필드 생성. 실패한 Vision 관측의 None을 0으로 바꾸지 않고 오류로 거절.
2. `prepare_agent_request(request_id, observation_ids, request_type, target_point)`: 현재 파일 기반 Bridge의 요청 형식 점검. 기본 임무 ID는 6개, 재관측 ID는 7개.
3. `validate_agent_reply(reply, request_id, reobservation=False)`: 이전 요청의 응답을 재사용하지 않도록 요청 ID 검증. 팀원 `reciver.py`에서 처리하는 행동만 통과시킴.

이 코드는 현재 스키마의 **검증·변환 예시이며 자동으로 기존 Agent/Go2를 연결하는 코드는 아니다.** 테스트용 참조 구현이다.

## 용어와 차이

- **Vision 정상 0개:** `OK` + count 0 = 추론은 성공했지만 검출 없음. 실제 객체 부재의 확증은 아님.
- **Vision 실패:** `FRAME_FAILED`/`INFERENCE_FAILED`에서는 count=None. 팀원 현재 DB 저장 경로에 함부로 0으로 넣지 않음. 실패 이벤트를 저장하는 DB 상태 컬럼은 별도 논의 필요.
- **초기 Agent 스키마:** `MOVE_TO/OBSERVE/RETRY/RETURN_HOME/STOP`, AUTO/ASK와 초기 A/B/HOME 사용.
- **최신 Agent 스키마:** `CONTINUE/REOBSERVE/CHANGE_VIEWPOINT/RETRY_NAVIGATION/ACCEPT_CHANGE/ABORT` 등. 현재 로봇 시나리오에서 자동 실행 가능한 행동은 더 제한적.
- **`bridge/agent_receiver.py`와 현재 `agent/local_llm.py`의 인자 불일치:** 이번 작업에서는 팀원 코드를 고치지 않음. `reciver.py` 경로를 기준으로 점검함.
- **실제 Vision/Go2 Closed-loop:** 여전히 실제 카메라·YOLO 결과를 사용하는 End-to-end 테스트가 필요. 시나리오의 재관측 결과는 Mock Vision임.

## 실행

```bash
python -m unittest discover -s tests -p 'test_go2_contract.py' -v
```

Python 3.10+ 사용. 테스트는 실제 Go2, Ollama, SQLite 및 Ultralytics 설치 없이 실행할 수 있도록 작성함.

## 향후 팀원과 확인할 항목

- 실제 통합에서 사용할 실행 진입점이 `test_scenario1.py` + `reciver.py`인지
- Vision 실패를 DB에 어떤 상태/컬럼으로 기록할지
- MBO-YOLO 탐지기 버전 및 운영 Confidence
- 실제 관측 완료 후 재관측 시 사용할 행동 허용 범위와 검증 방식
