"""
vision/detector.py

카메라 프레임에서 목표물(예: LAPTOP)이 있는지 확인하는 모듈.

다령 님 노션 메모: "카메라 영상 받아오고 객체 인식 및 분류 진행 예정,
파인튜닝 필요할 수도" → 아직 실제 모델은 붙기 전 상태입니다.

그래서 여기서도 llm_engine과 같은 전략을 씁니다:
- detect_target(): 실제 진입점. 지금은 모델이 없으므로 mock을 사용.
- 나중에 다령 님이 YOLO 등 모델을 붙이면 real_detect_target 안만 채우면 되고,
  main_agent.py 등 나머지 코드는 전혀 안 바뀝니다.

의존성(ultralytics 등)을 지금 요구하지 않도록, 실제 모델 import는
real_detect_target 함수 '안'에서만 합니다.
"""

# 실제 모델이 준비되면 True로 바꾸거나, 환경변수로 제어하세요.
USE_REAL_VISION = False


def real_detect_target(frame, target_label: str) -> bool:
    """
    실제 객체 탐지. frame(카메라 이미지)에서 target_label을 찾으면 True.
    다령 님이 모델을 정하면 이 함수 안만 구현하면 됩니다.

    예시(YOLO 사용 시):
        from ultralytics import YOLO
        model = YOLO("best.pt")            # 파인튜닝한 가중치
        results = model(frame)
        labels = [model.names[int(c)] for c in results[0].boxes.cls]
        return target_label.lower() in [l.lower() for l in labels]
    """
    raise NotImplementedError(
        "실제 Vision 모델이 아직 연결되지 않았습니다. "
        "USE_REAL_VISION=False로 두고 mock으로 테스트하세요."
    )


def mock_detect_target(frame, target_label: str) -> bool:
    """
    모델 없이 흐름을 검증하기 위한 더미.
    frame 자리에 'FOUND'/'NOT_FOUND' 같은 문자열을 넣어 결과를 강제할 수 있어
    시나리오 테스트에 편리합니다.
    """
    if isinstance(frame, str):
        return frame.upper() == "FOUND"
    # frame이 실제 이미지지만 mock 모드일 때는 '찾았다'고 가정
    return True


def detect_target(frame, target_label: str) -> bool:
    if USE_REAL_VISION:
        return real_detect_target(frame, target_label)
    return mock_detect_target(frame, target_label)
