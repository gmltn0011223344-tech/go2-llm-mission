# Vision 모듈

## 파일 구조

| 파일 | 역할 | 상태 |
|------|------|------|
| `detector.py` | 탐지 인터페이스 (mock) | 기존 코드. `USE_REAL_VISION=False` |
| `mbo_detector.py` | MBO-YOLO 기반 실제 탐지 모듈 | 김희수 구현 원본 |

## mbo_detector.py 의존성

### 필수 패키지

| 패키지 | 버전 | 비고 |
|--------|------|------|
| Python | 3.9 이상 | 3.14 미지원 (의존 패키지 호환성 문제) |
| OpenCV (`opencv-python` 또는 `opencv-python-headless`) | 4.x | 이미지 입출력 및 전처리 |
| NumPy | 1.x 또는 2.x | 배열 연산 |
| Ultralytics | **8.3.56 (커스텀 빌드)** | 아래 주의사항 참조 |

### 커스텀 Ultralytics 환경 (중요)

`mbo_detector.py`는 MBO-YOLO 저장소의 **커스텀 Ultralytics 8.3.56** 환경에서만 정상 동작합니다.

- 커밋: `001d65cc0d331e72cc47246e51f5e957dcfd8d27`
- `pip install -U ultralytics`로 공식 버전을 설치하면 `Addmodules`가 사라져 모델이 로드되지 않습니다
- 커스텀 Ultralytics는 MBO-YOLO 저장소에 포함되어 있으며, 해당 저장소를 clone한 뒤 `pip install -e .`로 설치해야 합니다

### 모델 가중치

- 파일: `mbo_final.pt` (MBO-YOLO 200 epoch 학습, 192 epoch 시점 최고 성능 가중치)
- 위치: `model/mbo_final.pt` 또는 프로젝트 루트의 `mbo_final.pt`
- 용량 문제로 이 저장소에 포함하지 않습니다
- 가중치 파일이 없으면 `INFERENCE_FAILED` 상태를 반환합니다

### 기존 환경과의 관계

- 기존 `requirements.txt`의 `anthropic>=1.0.0`은 agent 모듈용이며, vision 모듈과 충돌하지 않습니다
- `detector.py`(mock)는 추가 의존성 없이 동작합니다
- `mbo_detector.py`의 의존성(OpenCV, NumPy, 커스텀 Ultralytics)은 agent 모듈에 영향을 주지 않습니다

## 테스트

```bash
# 단위 테스트 (가짜 모델 사용, 가중치 불필요)
python -m unittest tests.test_mbo_detector -v

# 기존 AUTO/ASK 테스트
python -m unittest tests.test_auto_ask -v
```

### 테스트 검증 범위

**이 저장소의 테스트로 검증 가능:**
- 3-상태 반환 설계 (OK / FRAME_FAILED / INFERENCE_FAILED)
- 입력 타입별 처리 (파일 경로, ndarray, JPEG bytes, 흑백, BGRA)
- 에러 처리 (None, 빈 데이터, 손상 파일, 지원하지 않는 형식)
- 클래스별 개체수 집계 및 신뢰도 통계
- `to_observation()`, `to_flat_row()` 변환 함수
- 이미지 저장 기능
- blank_check 옵션

**실제 모델 가중치가 필요한 검증 (이 저장소에서 불가):**
- 실제 이미지에 대한 탐지 정확도 (mAP, Precision, Recall)
- 추론 속도 (inference_ms)
- 클래스 순서 일치 검증 (모델 로드 시 자동 확인)
- Notion에 기록된 31개 구조 테스트 (원본 테스트 코드 미확보)

## 3-상태 반환 설계

| 상태 | 의미 | counts 값 |
|------|------|-----------|
| `OK` | 정상적으로 추론 완료. 탐지 0개도 OK | 각 클래스별 정수 (0 이상) |
| `FRAME_FAILED` | 프레임 획득 실패 (카메라 오류, 손상 파일 등) | 전부 `None` |
| `INFERENCE_FAILED` | 프레임은 정상이나 모델 로드/추론 실패 | 전부 `None` |

**핵심:** OK에서 탐지 0개는 "정상적으로 추론했지만 해당 객체가 검출되지 않았다"는 뜻이며, 실제 객체의 부재가 확정된 것은 아닙니다.
