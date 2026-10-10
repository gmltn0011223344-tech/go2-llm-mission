# Go2 기반 해양생물 관측 및 LLM 자율 재관측 시스템

**Go2 Quadruped Robot · Object Detection · Observation Memory · LLM Agent**

4족 보행 로봇 Go2를 활용하여 해양생물의 개체수를 반복 관측하고, 관측 결과의 불일치가 발생했을 때 과거 관측 이력을 바탕으로 상황을 판단하여 후속 행동을 결정하는 캡스톤디자인 프로젝트입니다.

> **개발 진행 중 (2026.10 기준)**
>
> 현재 **이 GitHub 저장소**에는 초기 자연어 임무 계획·예외 대응 코드와 mock 기반 Vision 인터페이스가 있습니다. **별도 팀 개발 환경·실험 기록**에서는 Go2 관측지점 순회, SQLite 저장, 가상 관측 데이터 기반 Local LLM 판단 및 MBO-YOLO 탐지 모듈을 검증했습니다. 이 결과의 코드·실험 로그는 아직 모두 이 저장소에 반영되지 않았으며, 실제 카메라 입력부터 LLM 재관측 판단과 Go2 후속 행동까지의 Closed-loop 통합은 진행 중입니다.

---

## 1. 프로젝트 개요

### 개발 배경

로봇이 카메라를 이용해 동일한 장소를 반복 관측할 때, 탐지된 객체의 수가 이전과 다르게 나타날 수 있습니다. 그러나 이러한 차이가 반드시 실제 환경의 변화를 의미하지는 않습니다. 촬영 각도, 조명, 객체 가림, 객체 탐지 모델의 오인식 등으로 인해 관측 결과가 달라질 수 있습니다.

이 프로젝트에서 해결하려는 핵심 문제는 **"관측되지 않은 것"과 "실제로 존재하지 않는 것"을 구분하는 것**입니다. 단일 관측 결과만으로 변화를 확정하기보다, 과거 관측 기록을 활용하고 필요할 경우 재관측하는 판단 시스템을 개발하고자 합니다.

### 개발 목표

- Go2 로봇을 이용한 등록된 관측지점 순회 및 이미지 수집
- YOLO 기반 불가사리·가리비 탐지 및 개체수·신뢰도 추출
- SQLite 기반 Observation Memory에 관측 이력 시간순 저장
- Local LLM Agent를 이용한 현재 관측과 과거 이력 비교 판단
- 관측 이상 발생 시 재관측·시점 변경 등 후속 행동 선택
- Current-only Agent와 Temporal Memory Agent의 대조 실험

실험은 실제 해양 환경 대신 해양생물 사진을 인쇄하여 배치한 **실내 모의 관측 환경**을 대상으로 합니다.

## 2. 시스템 동작 (목표 흐름)

> 다음은 최종 통합 시스템의 **목표 동작 시나리오**이며, 현재 저장소만으로 전체 과정을 실행할 수 있다는 뜻은 아닙니다.

```
자연어 조사 명령
   ↓ 작업 분해
관측지점·작업 목록
   ↓
Go2 Navigation 이동 → 카메라 이미지 수집
   ↓
YOLO 객체 탐지 (개체수·종류·신뢰도)
   ↓
SQLite Observation Memory 저장
   ↓
Local LLM Agent (현재 관측 + 해당 지점 과거 이력 비교)
   ↓
상황 판단 → 후속 행동 결정
   ↓
CONTINUE / REOBSERVE / CHANGE_VIEWPOINT / RETRY_NAV / ASK_OPERATOR
   ↓
Go2 행동 수행 → 재관측 시 Memory에 추가 저장 → LLM 재판단
```

위 구조에서 Go2 카메라 영상 획득 → YOLO 추론 → DB 저장과 LLM 판단 결과 → Go2 재관측 행동 연결(Closed-loop)은 현재 구현 중입니다.

## 3. 프로젝트 진행 과정

> 진행 상태는 팀 Notion과 별도 실험 기록을 포함합니다. **구현 완료**가 반드시 이 저장소에 코드가 공개되어 있다는 뜻은 아닙니다.

본 프로젝트는 초기의 자연어 임무 수행·예외 대응 시스템에서 시계열 관측 기반 판단 시스템으로 개발 방향을 구체화했습니다.

| 단계 | 주요 내용 | 진행 상태 |
|------|----------|----------|
| 초기 임무 시스템 | 자연어 명령을 이동·탐색·복귀 작업으로 분해하는 계획기 구현 | 코드 구현 완료 (이 저장소) |
| 예외 대응 | AUTO/ASK 판단, 안전 규칙, Rule fallback | 코드 구현 완료 (이 저장소), 실제 API 검증 8/8 일치 (별도 실험) |
| Go2 순회 | P1_MAIN → P1_SIDE → P2_MAIN 2회 순회 | 실제 Go2 검증 완료 (별도 환경) |
| Observation Memory | SQLite에 관측 데이터 시간순 저장 | 구현 및 저장 검증 완료 (별도 환경) |
| Local LLM 판단 | 가상 관측 6건 기반 시계열 비교·이상 판단 | 가상 데이터 검증 완료 (별도 환경) |
| Vision detector | MBO-YOLO 기반 해양생물 탐지 모듈 | Mac 환경 실동작 검증 완료 (별도 환경) |
| MBO-YOLO 본 학습 | URPC2020 데이터셋 기반 200 epoch 학습 | Colab에서 학습 완료 (별도 환경) |
| 객체 탐지 모델 개선 | YOLO11n 파인튜닝 계획 | 데이터셋 구축 계획 수립 |
| Closed-loop 통합 | Go2 카메라 → YOLO → DB → LLM → 재관측 | 구현 필요 |

초기 버전의 자연어 임무 계획·예외 대응 시스템 상세는 [README_LLM_MODULE.md](README_LLM_MODULE.md)를 참고해 주세요.

## 4. 현재 구현된 기능

상세한 구현 내용, 실험 조건, 결과 분석은 [docs/](docs/) 폴더의 문서를 참고해 주세요.
- [docs/llm-agent.md](docs/llm-agent.md) — AUTO/ASK 판단 설계, 평가 방법, Local LLM 시계열 판단 실험
- [docs/object-detection.md](docs/object-detection.md) — MBO-YOLO 학습 과정, 탐지 성능 분석, YOLO11n 계획

### 4.1 자연어 임무 계획 및 예외 대응 (이 저장소)

자연어 명령을 순서 있는 작업 목록(JSON)으로 변환하고, 예외 발생 시 AUTO(자율 대응) 또는 ASK(사용자 확인) 판단을 수행하는 시스템입니다. 판단 경로, 검증 구조, 평가 방법의 상세는 [docs/llm-agent.md](docs/llm-agent.md)를 참고해 주세요.

- `agent/llm_engine.py` — 자연어 작업 분해 및 LLM 판단 (Anthropic API, mock 지원)
- `agent/mission_runner.py` — 임무 실행 흐름 제어
- `agent/rule_engine.py` — 안전 규칙 및 LLM 실패 시 대체 판단
- `agent/schema.py` — 행동 5종·상태 6종 정의, 등록 웨이포인트·물체, 출력 검증

**판단 경로 우선순위:**

```
오류/미등록? ──예──▶ 안전 규칙 (safety)
    │아니오
정상 상태? ──예──▶ 계획된 다음 작업 (plan)
    │아니오
LLM 판단 → 검증 통과? ──예──▶ LLM 결과 (llm)
                 │아니오
           규칙 대체 → 검증 통과? ──예──▶ 규칙 결과 (fallback)
                          │아니오
                        안전 정지 (safety)
```

**실제 API 검증 결과 (2026-09-23, 별도 실험 기록 기준):**
- 8개 예외 시나리오 판단: 8/8 정답 일치
- 판단 경로 3종 확인: LLM 직접 판단 4건, 안전 규칙 선차단 2건, 규칙 대체 2건
- 2회 반복 실행 시 근거 문장은 상이하나 판단 결과는 동일

이 저장소에는 판단 평가 코드(`run_auto_ask_eval.py`)와 정답표(`agent/evaluation.py`)가 포함되어 있습니다. `ANTHROPIC_API_KEY` 없이 실행하면 mock 판단을 사용하며, mock 결과는 LLM 성능이 아닌 코드·채점 로직 점검용입니다.

### 4.2 Go2 순회 및 Observation Memory (별도 환경에서 검증)

황다령 구현. 현재 이 저장소에 소스가 포함되어 있지 않습니다.

- Go2와 WebRTC DataChannel 통신
- `P1_MAIN → P1_SIDE → P2_MAIN` 3개 관측지점 순차 이동 및 도착 확인 (2회 연속 순회 성공)
- 각 관측지점 도착 시 `x, y, z, yaw` 및 Navigation 상태 수신, 안정화 후 Observation Snapshot 생성
- SQLite Observation Memory에 관측 시각, 위치, 상태, 탐지 결과 저장
- 2회 순회 완료 후 `agent_request.json` 생성 → Local LLM Agent 전달

### 4.3 Local LLM Agent (별도 환경에서 검증)

아래 결과는 별도 실험 환경의 기록이며, 현재 GitHub의 `agent/llm_engine.py`(Anthropic API 기반 초기 버전)와는 다른 구현입니다.

- MacBook Air M4에서 Ollama `qwen3.5:4b` 실행
- JSON Schema로 출력 형식 제한 (상황 코드·행동 코드·대상 관측지점)
- 동일 입력 20회 반복: JSON 파싱·스키마 검증 전부 통과, 평균 응답 9.9초
- 가상 관측 데이터 6건(3지점 × 2회차) 기반 시계열 비교 검증 완료
- 2회차 P1에 `starfish 3→0`, confidence `0.91→0.38` 이상 삽입 → `OBSERVATION_ANOMALY → REOBSERVE → P1_MAIN` 판단 확인

이 검증은 가상 관측 데이터를 SQLite에 저장하고 LLM이 시계열 비교 판단을 수행한 것이며, 실제 Go2 Closed-loop 통합과는 별도의 단계입니다.

### 4.4 객체 탐지

자세한 학습 과정, 성능 분석, 탐지 테스트 결과는 [docs/object-detection.md](docs/object-detection.md)를 참고해 주세요.

**MBO-YOLO 학습 (Colab, 별도 환경):**
- URPC2020 데이터셋: 학습 5,541장 / 검증 1,200장 / 테스트 800장
- 환경: Google Colab Tesla T4, 커스텀 Ultralytics 8.3.56
- 총 200 epoch 학습 중 192번째 epoch에서 최고 검증 성능 기록 → 해당 가중치를 `mbo_final.pt`로 선택
- 192~199 epoch 구간의 성능 변화가 미미하여 현재 데이터와 설정에서의 수렴으로 판단

| Precision | Recall | mAP50 | mAP50-95 |
|-----------|--------|-------|----------|
| 0.764 | 0.591 | 0.677 | 0.387 |

**Vision Detector (`vision/mbo_detector.py`, 별도 환경):**
- MBO-YOLO 최종 모델을 사용하는 탐지 모듈 (김희수 구현)
- OK / FRAME_FAILED / INFERENCE_FAILED 3-상태 반환 — OK에서 탐지 0개는 "정상 추론했지만 검출되지 않았다"는 뜻이며 실제 부재가 확정된 것은 아님
- 구조 테스트: 가짜 모델로 31개 항목 검사 → 31개 통과
- 이 파일은 현재 GitHub에 반영되지 않았습니다

**YOLO11n 파인튜닝 (계획 단계):**
- 실험 환경에 적합한 데이터셋을 자체 구축하여 YOLO11n을 파인튜닝하는 방향을 수립
- 탐지 클래스: starfish, scallop (2개)
- 초기 목표: 약 200장 (Train 140 / Val 30 / Test 30)

## 5. 테스트 및 실행

```bash
# 패키지 설치
python3 -m pip install -r requirements.txt

# 단위 테스트 (9개, mock 기반)
python3 -m unittest tests.test_auto_ask

# Rule 기반 예외 대응 평가
python3 run_auto_ask_eval.py --rule

# LLM 판단 평가 (ANTHROPIC_API_KEY 필요, 없으면 mock)
python3 run_auto_ask_eval.py
```

**주의사항:**
- `ANTHROPIC_API_KEY`가 없으면 mock 판단을 사용합니다. mock 결과는 LLM 성능이 아닌 코드·채점 로직 점검용입니다.
- `main_llm.py`의 실제 로봇 실행에는 팀원의 별도 로봇 코드 및 Go2 실행 환경이 필요합니다.
- Python 3.12 가상환경 권장.

## 6. 프로젝트 파일 구조

| 파일 및 폴더 | 설명 |
|-------------|------|
| `agent/llm_engine.py` | 자연어 작업 분해 및 LLM 판단 (Anthropic API / mock) |
| `agent/mission_runner.py` | 임무 실행 흐름 제어 |
| `agent/rule_engine.py` | 안전 규칙 및 대체 판단 |
| `agent/schema.py` | 행동·상태 정의와 출력 검증 |
| `agent/evaluation.py` | AUTO/ASK 정답표와 채점 |
| `agent/state_adapter.py` | Navigation 상태값 변환 |
| `agent/robot_executor.py` | Go2 실행부 연결 인터페이스 |
| `agent/sim_executor.py` | 모의 실행 환경 |
| `vision/detector.py` | 탐지 인터페이스 (mock 포함) |
| `tests/test_auto_ask.py` | AUTO/ASK 관련 단위 테스트 (9개) |
| `run_auto_ask_eval.py` | 예외 대응 판단 평가 |
| `run_comparison.py` | 초기 Rule/LLM 비교 참고 코드 |
| `main_llm.py` | 실제 로봇 연동 실행 진입점 |
| `README_LLM_MODULE.md` | 초기 자연어 임무 계획·예외 대응 시스템 상세 설명 |
| `docs/` | 객체 탐지(`object-detection.md`)와 LLM Agent(`llm-agent.md`) 상세 문서 |

**별도 개발 환경에 있으며 현재 이 저장소에 미반영:**
- `vision/mbo_detector.py` — MBO-YOLO 기반 탐지 모듈 (김희수 구현)
- Local LLM 판단 실험 코드 — Ollama `qwen3.5:4b` 기반 시계열 판단
- Go2 WebRTC 통신·순회·SQLite 저장 코드 — 황다령 구현
- MBO-YOLO 학습 코드 및 `mbo_final.pt` 가중치

## 7. 팀 구성 및 담당 영역

본 프로젝트는 2인 캡스톤디자인 팀 프로젝트입니다.

**김희수:**
- 자연어 임무 계획 및 AUTO/ASK 예외 대응
- Local LLM 선정·실행 및 Temporal Memory 판단 실험
- MBO-YOLO Colab 본 학습, epoch별 성능 분석 및 수렴 판단
- `mbo_detector.py` 구현과 구조 테스트
- LLM·Vision 관련 평가 코드 및 실험

**황다령:**
- Go2 연결·Navigation·WebRTC 통신
- 관측지점 순회 및 로봇 상태 수신
- SQLite Observation Memory 저장 연동
- 실제 로봇 실험 환경 구축

**공동 작업:**
- 객체 탐지 추론 결과 검토
- YOLO11n 파인튜닝용 데이터셋 구축
- 실험 시나리오 설계
- 시스템 통합 및 최종 평가

## 8. 현재 한계 및 개발 현황

1. Go2의 관측지점 순회·SQLite 저장 및 가상 관측 데이터 기반 Local LLM 판단은 팀 별도 환경에서 검증되었으나, 관련 소스와 실험 로그가 이 공개 저장소에 모두 반영된 것은 아닙니다.
2. MBO-YOLO는 URPC2020 수중 데이터 기반이라 일반 환경·인쇄물에서의 탐지 성능이 낮아, YOLO11n 파인튜닝을 준비하고 있습니다.
3. LLM 판단 결과를 Go2 재관측 행동으로 연결하는 Closed-loop은 아직 구현되지 않았습니다.
4. 간헐적인 `NO_PATH` Navigation 오류가 관찰되며 원인 조사 중입니다.
5. 초기 AUTO/ASK 시스템(Anthropic API)과 Temporal Memory 판단 시스템(Local LLM)의 통합이 필요합니다.

향후 코드, 실험 결과 및 재현 가능한 실행 환경을 단계적으로 정리하고 문서를 갱신할 예정입니다.

---

**Project Type:** University Capstone Design (한국해양대학교 인공지능공학부)
**Development Period:** 2026.09– (진행 중)
**Main Technologies:** Python, Go2 (Unitree), MBO-YOLO, YOLO11n, SQLite, Ollama (qwen3.5:4b), Anthropic API
