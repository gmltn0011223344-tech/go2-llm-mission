# Local LLM 구조화 출력 실험

## 개요

외부 LLM API(Anthropic) 대신 **로컬에서 실행 가능한 LLM**으로 Agent 판단 모듈을 구동할 수 있는지 검증한 실험입니다.

기존 `agent/` 모듈은 Anthropic Claude API를 사용하지만, 실제 Go2 운용 환경(연구실 PC 또는 Jetson)에서는 네트워크 없이 로컬 추론이 필요할 수 있습니다. 이 실험은 Ollama를 통해 로컬 LLM의 **JSON Schema 구조화 출력 안정성**을 확인합니다.

## 실험 환경

| 항목 | 내용 |
|------|------|
| 모델 | `qwen3.5:4b` |
| 실행 환경 | MacBook Air M4, Ollama |
| 호출 방식 | Python `ollama` 패키지, 로컬 API |
| 출력 제어 | JSON Schema (`format` 파라미터) |

## 파일

| 파일 | 설명 |
|------|------|
| `test_json_20.py` | 같은 입력을 20회 반복해 JSON 파싱 및 스키마 검증을 수행하는 테스트 |

## test_json_20.py 상세

### 목적

Local LLM이 **매 호출마다 파싱 가능한 JSON을 반환하고, 정해진 스키마를 지키는지** 확인합니다.

> **주의:** 이 테스트는 출력 형식 검증이며, 상황 판단의 정확도를 확인한 결과가 아닙니다.

### 테스트 스키마

해양생물 조사 시나리오의 판단 출력 형식입니다.

```json
{
  "situation": "NORMAL | OBSERVATION_ANOMALY | POSSIBLE_REAL_CHANGE | NAV_FAILURE",
  "action": "CONTINUE | REOBSERVE | CHANGE_VIEWPOINT | RETRY_NAV",
  "reason": "판단 근거 (한국어 한 문장)"
}
```

이 스키마는 기존 `agent/schema.py`의 AUTO/ASK 체계와는 다른 **새로운 설계**입니다.

| 구분 | 기존 (`agent/schema.py`) | 새 설계 (`test_json_20.py`) |
|------|--------------------------|----------------------------|
| 판단 대상 | 자율 대응 vs 사용자 확인 | 관측 상황 분류 |
| 상황 코드 | REACHED, NO_PATH 등 (실행부 상태) | NORMAL, OBSERVATION_ANOMALY 등 (관측 판단) |
| 행동 코드 | MOVE_TO, OBSERVE 등 (로봇 명령) | CONTINUE, REOBSERVE 등 (조사 전략) |
| 핵심 질문 | "스스로 할까, 사용자에게 물을까?" | "관측 이상인가, 실제 변화인가?" |

### 테스트 입력

B 지점 불가사리 관측 시나리오 (고정 입력, 20회 동일):

```json
{
  "site": "B",
  "species": "starfish",
  "baseline_count": 8,
  "current_observation": {
    "viewpoint": "B_MAIN",
    "count": 3,
    "confidence": 0.4
  },
  "same_view_reobserve_count": 0,
  "alternate_view_observations": [],
  "nav_state": "OK"
}
```

기대 판단: baseline 8 → 현재 3 (차이 5), confidence 0.4 (낮음), 재관측 0회, 다른 시야 미확인 → `OBSERVATION_ANOMALY` / `REOBSERVE`

### 검증 결과 (Notion 10/6 기록)

| 항목 | 결과 |
|------|------|
| JSON 파싱 성공 | 20/20 (100%) |
| 스키마 검증 통과 | 20/20 (100%) |
| 평균 응답 시간 | 9.9초 |
| 통과 기준 | 90% (18/20) 이상 → **통과** |

### 실행 방법

```bash
# Ollama가 실행 중이고 qwen3.5:4b 모델이 설치된 환경에서
pip install ollama
python experiments/local_llm/test_json_20.py
```

> 이 저장소의 CI/CD 환경에서는 Ollama가 없으므로 실행되지 않습니다.

## 기존 모듈과의 관계

- `agent/` 모듈: Anthropic Claude API 기반, AUTO/ASK 판단 구조
- `experiments/local_llm/`: Ollama 기반, 새 해양생물 조사 판단 구조

두 모듈은 독립적이며 의존성이 없습니다. Local LLM 실험은 향후 `agent/` 모듈의 LLM 엔진을 Ollama로 교체하거나, 새 판단 스키마를 적용할 때의 기반이 됩니다.

## 다음 단계 (계획)

1. 실제 Go2 운용 장비 (연구실 PC 또는 Jetson)에서 Ollama 실행 확인
2. 상황 판단 정확도 테스트 (형식이 아닌 판단 내용 검증)
3. Observation Memory (SQLite)와 연결한 시계열 입력 테스트
