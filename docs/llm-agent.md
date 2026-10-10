# LLM Agent 상세

> 이 문서는 자연어 임무 계획·예외 대응 시스템(AUTO/ASK)과 Local LLM 시계열 판단 실험의 상세 설계와 검증 결과를 정리합니다.
> 프로젝트 전체 개요는 [README.md](../README.md)를 참고해 주세요.

---

## 1. 자연어 임무 계획 (이 저장소)

### 1.1 작업 분해

사용자의 자연어 명령을 순서 있는 작업 목록(JSON)으로 변환합니다.

**입력:** `"A 지점으로 가서 병이 있는지 확인하고 돌아와"`

**출력:**
```json
{
  "tasks": [
    {"action": "MOVE_TO", "target": "A"},
    {"action": "OBSERVE", "target": "BOTTLE"},
    {"action": "RETURN_HOME", "target": "HOME"}
  ]
}
```

사용 가능한 행동은 5종으로 제한됩니다:

| 행동 | 설명 |
|------|------|
| MOVE_TO | target 위치로 이동 |
| OBSERVE | 현재 위치에서 target 물체 확인 (재촬영 포함) |
| RETRY | 직전 작업을 한 번 더 시도 |
| RETURN_HOME | 시작 지점으로 복귀 |
| STOP | 안전 정지 |

LLM 출력은 JSON Schema로 형식을 제한하며 (`agent/llm_engine.py`의 `PLAN_SCHEMA`), 검증을 통과하지 못한 출력은 실행되지 않습니다.

### 1.2 등록된 대상

| 구분 | 등록 목록 | 정의 위치 |
|------|----------|----------|
| 웨이포인트 | A, B, HOME | `agent/schema.py` `REGISTERED_WAYPOINTS` |
| 탐색 물체 | BOTTLE, BACKPACK, CHAIR, LAPTOP | `agent/schema.py` `ALLOWED_OBJECTS` |

등록되지 않은 목적지나 물체가 명령에 포함되면, 작업 계획 검증 단계에서 거부하고 사용자에게 확인을 요청합니다 (임의로 이동하지 않음).

---

## 2. AUTO/ASK 예외 대응 시스템 (이 저장소)

### 2.1 판단 경로 (우선순위)

작업 실행 중 예외 상태가 발생하면, 다음 우선순위로 판단합니다:

```
1. 안전 규칙 (safety)
   ERROR → 즉시 STOP
   미등록 목적지 → ASK (LLM을 거치지 않음)

2. 정상 상태 (plan)
   REACHED / TARGET_FOUND → 계획된 다음 작업 수행

3. 예외 상태 판단
   LLM 판단 → 출력 검증 → 통과하면 실행 (llm)
                          → 실패하면 Rule 대체 (fallback)
                                    → 그래도 실패하면 안전 정지 (safety)
```

판단의 핵심 원칙:
- **AUTO:** 위험이 낮고 해결 방법이 명확할 때 로봇이 자율 판단 (첫 번째 경로 실패 → RETRY 등)
- **ASK:** 반복 실패, 미등록 목적지, 대체 목적지 필요, 판단 불확실 시 사용자 확인 요청
- ASK 상태에서는 사용자 승인 전까지 어떤 행동도 실행하지 않음

### 2.2 안전 검증 흐름

LLM 출력은 실행 전에 반드시 검증을 거칩니다 (`agent/schema.py` `validate_action_output`):

- mode가 AUTO/ASK 중 하나인지
- 행동이 허용된 5종 중 하나인지
- MOVE_TO/OBSERVE에 target이 있는지
- RETURN_HOME의 target이 HOME인지
- 이동 대상이 등록된 웨이포인트인지
- 탐색 대상이 허용된 물체인지
- ASK일 때 next_action이 null이고 질문이 있는지

검증 실패 시 Rule 대체 판단을 시도하고, 그래도 검증을 통과하지 못하면 안전 정지합니다.

### 2.3 재시도 한도

`max_retry` (기본값 1)를 초과하는 AUTO 재시도는 검증 단계에서 차단됩니다. LLM이 "계속 RETRY하겠다"고 판단하더라도, 이미 한도를 넘었으면 Rule이 ASK로 대체합니다.

---

## 3. 판단 평가 (이 저장소)

### 3.1 정답표

8개 예외 시나리오에 대한 기대 판단을 미리 정의하여 평가 기준으로 사용합니다 (`agent/evaluation.py`):

| 시나리오 | 상태 | 핵심 조건 | 기대 판단 |
|---------|------|----------|----------|
| 시간초과 첫 발생 | TIMEOUT | retry_count=0 | AUTO |
| 경로실패 첫 발생 | NO_PATH | retry_count=0 | AUTO |
| 경로실패 반복 | NO_PATH | retry_count=1 | ASK |
| 미발견·재촬영 가능 | TARGET_NOT_FOUND | retry_count=0 | AUTO |
| 미발견 반복 | TARGET_NOT_FOUND | retry_count=1 | ASK |
| 미등록 목적지 | NO_PATH | registered=False | ASK |
| 대체 목적지 필요 | NO_PATH | needs_alternative=True | ASK |
| 시스템 오류 | ERROR | — | STOP |

### 3.2 평가 방법

`run_auto_ask_eval.py`는 두 단계로 평가합니다:

**판단 평가:** 8개 시나리오에 대해 AUTO/ASK/STOP 판단을 채점. ASK 기준 Precision, Recall, F1을 산출합니다.

**임무 평가:** 시뮬레이터(`agent/sim_executor.py`)로 6가지 임무 시나리오를 실행하여 종료 상태를 확인합니다.

| 임무 시나리오 | 조건 | 기대 동작 |
|-------------|------|----------|
| 정상 | 오류 없음 | MISSION_COMPLETED |
| 경로실패 1회 | A에서 NO_PATH, 재시도 시 복구 | AUTO RETRY 후 완료 |
| 경로실패 반복 | A에서 NO_PATH, 복구 불가 | ASK_PENDING |
| 미발견 1회 | BOTTLE에서 TARGET_NOT_FOUND, 재시도 시 발견 | AUTO OBSERVE 후 완료 |
| 미발견 반복 | BOTTLE에서 TARGET_NOT_FOUND, 복구 불가 | ASK_PENDING |
| 오류 | A에서 ERROR | STOPPED |

### 3.3 실제 API 검증 결과

> 아래 결과는 2026-09-23 별도 실험 기록 기준이며, `ANTHROPIC_API_KEY`를 사용한 실제 API 호출 결과입니다.

- 8개 예외 시나리오 판단: **8/8 정답 일치**
- 판단 경로 3종 확인: LLM 직접 판단 4건, 안전 규칙 선차단 2건, 규칙 대체 2건
- 2회 반복 실행 시 근거 문장(reason)은 상이하나 판단 결과(AUTO/ASK/STOP)는 동일

`ANTHROPIC_API_KEY` 없이 실행하면 mock 판단을 사용합니다. mock은 내부적으로 Rule 엔진과 동일한 로직을 사용하므로, 코드·채점 로직의 정상 동작을 확인하는 용도입니다.

---

## 4. Local LLM 시계열 판단 실험 (별도 환경)

> 아래 내용은 별도 실험 환경의 기록이며, 이 저장소의 코드(`agent/llm_engine.py`, Anthropic API 기반)와는 다른 구현입니다.

### 4.1 실험 환경

| 항목 | 내용 |
|------|------|
| 하드웨어 | MacBook Air M4 |
| LLM | Ollama `qwen3.5:4b` |
| 출력 형식 | JSON Schema 제한 (상황 코드·행동 코드·대상 관측지점) |
| 데이터 소스 | SQLite Observation Memory |
| 입력 | 가상 관측 데이터 6건 (3지점 x 2회차) |

### 4.2 가상 관측 데이터

Go2를 사용할 수 없는 상황에서 시스템 흐름을 검증하기 위해, P1_MAIN, P1_SIDE, P2_MAIN 3개 관측지점에 대한 2회차 가상 관측 데이터를 생성하여 SQLite에 저장했습니다 (ID 11~16).

**이상 삽입:** 2회차 P1_MAIN에서 `starfish 3→0`, confidence `0.91→0.38`으로 의도적 이상 상황을 삽입했습니다.

### 4.3 검증 결과

- JSON 파싱·스키마 검증: 동일 입력 20회 반복에서 **전부 통과**
- 평균 응답 시간: **9.9초**
- 이상 판단: `OBSERVATION_ANOMALY → REOBSERVE → P1_MAIN` 판단 확인

LLM이 1회차와 2회차의 관측 데이터를 비교하여, 불가사리 개체수 급감과 신뢰도 하락을 이상으로 판단하고, 해당 지점의 재관측을 지시하는 것을 확인했습니다.

### 4.4 초기 시스템과의 차이

| 항목 | 초기 시스템 (이 저장소) | Temporal Memory 시스템 (별도 환경) |
|------|----------------------|-------------------------------|
| LLM | Anthropic API (claude-sonnet) | Ollama qwen3.5:4b (로컬) |
| 판단 입력 | 현재 상태값 + retry_count | 현재 관측 + 해당 지점 과거 이력 |
| 판단 기준 | 실패 횟수 기반 AUTO/ASK | 시계열 비교 기반 이상 탐지 |
| 후속 행동 | RETRY, OBSERVE, RETURN_HOME 등 | REOBSERVE, CHANGE_VIEWPOINT 등 |
| 데이터 저장 | 없음 | SQLite Observation Memory |

두 시스템의 통합은 향후 과제입니다.

### 4.5 Current-only vs Temporal Memory 비교 실험 (계획)

동일한 관측 데이터에 대해 과거 이력 없이 현재 관측만으로 판단하는 에이전트와, 시계열 관측 이력을 활용하는 에이전트의 판단 품질을 비교하는 대조 실험을 계획하고 있습니다.

---

## 5. 관련 코드 (이 저장소)

| 파일 | 역할 |
|------|------|
| `agent/llm_engine.py` | 자연어 작업 분해 및 LLM 판단 (Anthropic API / mock) |
| `agent/mission_runner.py` | 임무 실행 흐름 제어, 판단 경로 우선순위 관리 |
| `agent/rule_engine.py` | 안전 규칙 (ERROR·미등록) 및 LLM 실패 시 대체 판단 |
| `agent/schema.py` | 행동 5종·상태 6종 정의, 등록 웨이포인트·물체, 출력 검증 |
| `agent/evaluation.py` | 8개 시나리오 정답표 및 ASK 기준 Precision/Recall/F1 채점 |
| `agent/sim_executor.py` | 모의 실행 환경 (scripted 오류 주입 지원) |
| `run_auto_ask_eval.py` | 판단 평가 + 임무 평가 실행 스크립트 |
| `tests/test_auto_ask.py` | AUTO/ASK 관련 단위 테스트 (9개) |

**별도 환경에 있으며 이 저장소에 미반영:**

| 파일 | 역할 |
|------|------|
| Local LLM 판단 코드 | Ollama qwen3.5:4b 기반 시계열 판단 |
| `agent_receiver.py` | agent_request.json 수신, SQLite 조회, LLM 전달 |
| SQLite Observation Memory 코드 | 관측 데이터 시간순 저장·조회 |
