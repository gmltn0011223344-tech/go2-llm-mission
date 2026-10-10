"""
tests/test_mbo_detector.py
MBODetector 단위 테스트

가짜 모델(FakeModel)을 주입하여 실제 가중치 파일 없이 인터페이스를 검증합니다.
Notion에 기록된 31개 구조 테스트와는 별도로 새로 작성한 테스트입니다.

실제 모델 가중치(mbo_final.pt)와 커스텀 Ultralytics 8.3.56 환경이 없으므로,
모델 로드·추론 정확도(mAP 등)는 이 테스트에서 검증하지 않습니다.
"""

import json
import os
import shutil
import tempfile
import unittest

import cv2
import numpy as np

from vision.mbo_detector import (
    CLASS_NAMES,
    STATUS_FRAME_FAILED,
    STATUS_INFERENCE_FAILED,
    STATUS_OK,
    MBODetector,
    to_flat_row,
    to_observation,
)


# ---------------------------------------------------------------- 가짜 모델
class FakeBox:
    """Ultralytics Results.boxes 를 흉내낸다."""

    def __init__(self, cls_list, conf_list, xyxy_list):
        self.cls = np.array(cls_list, dtype=np.float32)
        self.conf = np.array(conf_list, dtype=np.float32)
        self.xyxy = np.array(xyxy_list, dtype=np.float32)

    def __len__(self):
        return len(self.cls)


class FakeResult:
    """model.predict() 가 돌려주는 Results 객체 1개를 흉내낸다."""

    def __init__(self, boxes: FakeBox):
        self.boxes = boxes


class FakeModel:
    """MBODetector 에 주입할 가짜 YOLO 모델."""

    def __init__(self, detections=None, raise_on_predict=False):
        """
        detections: [(class_id, confidence, [x1,y1,x2,y2]), ...]
        raise_on_predict: True 이면 predict() 에서 예외 발생
        """
        self._detections = detections or []
        self._raise_on_predict = raise_on_predict
        # MBODetector._load_model 에서 클래스 순서 검증에 사용
        self.names = dict(CLASS_NAMES)

    def predict(self, **kwargs):
        if self._raise_on_predict:
            raise RuntimeError("Fake predict failure")
        if not self._detections:
            return [FakeResult(FakeBox([], [], []))]
        cls_list = [d[0] for d in self._detections]
        conf_list = [d[1] for d in self._detections]
        xyxy_list = [d[2] for d in self._detections]
        return [FakeResult(FakeBox(cls_list, conf_list, xyxy_list))]


def make_detector(detections=None, raise_on_predict=False, **kwargs):
    """테스트용 MBODetector 를 만든다. 가짜 모델을 주입한다."""
    model = FakeModel(detections=detections, raise_on_predict=raise_on_predict)
    defaults = dict(weights="dummy.pt", save_images=False, model=model)
    defaults.update(kwargs)
    return MBODetector(**defaults)


# ---------------------------------------------------------------- 테스트 이미지 생성
def make_bgr_frame(width=640, height=480, color=(128, 64, 32)):
    """단색이 아닌 BGR ndarray 를 만든다. (blank_check 통과용으로 노이즈 추가)"""
    frame = np.full((height, width, 3), color, dtype=np.uint8)
    # std > 1.0 이 되도록 약간의 노이즈
    frame[0, 0] = (0, 0, 0)
    frame[0, 1] = (255, 255, 255)
    return frame


def make_jpeg_bytes(frame=None):
    """BGR ndarray 를 JPEG bytes 로 인코딩한다."""
    if frame is None:
        frame = make_bgr_frame()
    _, buf = cv2.imencode(".jpg", frame)
    return buf.tobytes()


class TestMBODetectorStatus(unittest.TestCase):
    """3-상태(OK / FRAME_FAILED / INFERENCE_FAILED) 반환 검증."""

    # ---- OK 상태 ----

    def test_ok_with_detections(self):
        """정상 추론 + 탐지 있음 → OK"""
        det = make_detector(detections=[
            (3, 0.85, [10, 20, 100, 200]),  # starfish
            (2, 0.72, [50, 60, 150, 250]),  # scallop
        ])
        result = det.detect(make_bgr_frame())
        self.assertEqual(result["status"], STATUS_OK)
        self.assertEqual(result["total_count"], 2)
        self.assertIsNone(result["error"])

    def test_ok_with_zero_detections(self):
        """정상 추론 + 탐지 0개 → OK (실제 부재 확정이 아님)"""
        det = make_detector(detections=[])
        result = det.detect(make_bgr_frame())
        self.assertEqual(result["status"], STATUS_OK)
        self.assertEqual(result["total_count"], 0)
        self.assertEqual(result["detections"], [])
        # counts 는 전부 0 이어야 한다 (None 이 아님)
        for name in CLASS_NAMES.values():
            self.assertEqual(result["counts"][name], 0)
        self.assertIsNone(result["error"])

    # ---- FRAME_FAILED 상태 ----

    def test_frame_failed_none_input(self):
        """입력 None → FRAME_FAILED"""
        det = make_detector()
        result = det.detect(None)
        self.assertEqual(result["status"], STATUS_FRAME_FAILED)
        self.assertIsNotNone(result["error"])
        self.assertEqual(result["error"]["code"], "FRAME_NONE")

    def test_frame_failed_nonexistent_file(self):
        """존재하지 않는 파일 경로 → FRAME_FAILED"""
        det = make_detector()
        result = det.detect("/nonexistent/path/image.jpg")
        self.assertEqual(result["status"], STATUS_FRAME_FAILED)
        self.assertEqual(result["error"]["code"], "FILE_NOT_FOUND")

    def test_frame_failed_empty_ndarray(self):
        """크기 0인 ndarray → FRAME_FAILED"""
        det = make_detector()
        result = det.detect(np.array([], dtype=np.uint8))
        self.assertEqual(result["status"], STATUS_FRAME_FAILED)
        self.assertEqual(result["error"]["code"], "FRAME_EMPTY")

    def test_frame_failed_empty_bytes(self):
        """빈 bytes → FRAME_FAILED"""
        det = make_detector()
        result = det.detect(b"")
        self.assertEqual(result["status"], STATUS_FRAME_FAILED)
        self.assertEqual(result["error"]["code"], "FRAME_EMPTY")

    def test_frame_failed_blank_frame(self):
        """완전 단색(검은 화면) → FRAME_FAILED"""
        det = make_detector()
        black = np.zeros((480, 640, 3), dtype=np.uint8)
        result = det.detect(black)
        self.assertEqual(result["status"], STATUS_FRAME_FAILED)
        self.assertEqual(result["error"]["code"], "FRAME_BLANK")

    def test_frame_failed_bad_type(self):
        """지원하지 않는 입력 타입 → FRAME_FAILED"""
        det = make_detector()
        result = det.detect(12345)
        self.assertEqual(result["status"], STATUS_FRAME_FAILED)
        self.assertEqual(result["error"]["code"], "FRAME_BAD_TYPE")

    def test_frame_failed_bad_ndarray_shape(self):
        """지원하지 않는 ndarray 모양 → FRAME_FAILED"""
        det = make_detector()
        weird = np.zeros((10, 10, 5), dtype=np.uint8)
        result = det.detect(weird)
        self.assertEqual(result["status"], STATUS_FRAME_FAILED)
        self.assertEqual(result["error"]["code"], "FRAME_BAD_SHAPE")

    def test_frame_failed_bad_dtype(self):
        """uint8 이 아닌 ndarray → FRAME_FAILED"""
        det = make_detector()
        frame = np.zeros((480, 640, 3), dtype=np.float32)
        frame[0, 0] = (1.0, 1.0, 1.0)  # std > 0 이지만 dtype 이 문제
        result = det.detect(frame)
        self.assertEqual(result["status"], STATUS_FRAME_FAILED)
        self.assertEqual(result["error"]["code"], "FRAME_BAD_DTYPE")

    # ---- INFERENCE_FAILED 상태 ----

    def test_inference_failed_predict_error(self):
        """모델 predict() 예외 → INFERENCE_FAILED"""
        det = make_detector(raise_on_predict=True)
        result = det.detect(make_bgr_frame())
        self.assertEqual(result["status"], STATUS_INFERENCE_FAILED)
        self.assertEqual(result["error"]["code"], "PREDICT_FAILED")

    def test_inference_failed_model_load_error(self):
        """모델 로드 실패 → INFERENCE_FAILED"""
        # model=None + 존재하지 않는 가중치 경로 → _load_model 에서 FileNotFoundError
        det = MBODetector(weights="/nonexistent/model.pt", save_images=False)
        result = det.detect(make_bgr_frame())
        self.assertEqual(result["status"], STATUS_INFERENCE_FAILED)
        self.assertEqual(result["error"]["code"], "MODEL_LOAD_FAILED")


class TestMBODetectorInputTypes(unittest.TestCase):
    """다양한 입력 타입(파일 경로, ndarray, JPEG bytes) 검증."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.det = make_detector(detections=[
            (3, 0.90, [10, 20, 100, 200]),
        ])

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_input_file_path(self):
        """파일 경로 입력 → OK"""
        path = os.path.join(self.tmpdir, "test.jpg")
        cv2.imwrite(path, make_bgr_frame())
        result = self.det.detect(path)
        self.assertEqual(result["status"], STATUS_OK)
        self.assertEqual(result["image"]["source_type"], "path")

    def test_input_ndarray_bgr(self):
        """BGR ndarray 입력 → OK"""
        result = self.det.detect(make_bgr_frame())
        self.assertEqual(result["status"], STATUS_OK)
        self.assertEqual(result["image"]["source_type"], "ndarray")

    def test_input_ndarray_grayscale(self):
        """흑백 ndarray → BGR 변환 후 OK"""
        rng = np.random.RandomState(42)
        gray = rng.randint(0, 256, (480, 640), dtype=np.uint8)
        result = self.det.detect(gray)
        self.assertEqual(result["status"], STATUS_OK)
        self.assertEqual(result["image"]["source_type"], "ndarray")

    def test_input_ndarray_bgra(self):
        """BGRA ndarray → BGR 변환 후 OK"""
        rng = np.random.RandomState(42)
        bgra = rng.randint(0, 256, (480, 640, 4), dtype=np.uint8)
        result = self.det.detect(bgra)
        self.assertEqual(result["status"], STATUS_OK)

    def test_input_jpeg_bytes(self):
        """JPEG bytes 입력 → OK"""
        result = self.det.detect(make_jpeg_bytes())
        self.assertEqual(result["status"], STATUS_OK)
        self.assertEqual(result["image"]["source_type"], "bytes")

    def test_input_invalid_bytes(self):
        """디코딩 불가능한 bytes → FRAME_FAILED"""
        result = self.det.detect(b"not_a_real_image_data")
        self.assertEqual(result["status"], STATUS_FRAME_FAILED)
        self.assertEqual(result["error"]["code"], "IMAGE_DECODE_FAILED")

    def test_input_corrupt_file(self):
        """이미지로 읽을 수 없는 파일 → FRAME_FAILED"""
        path = os.path.join(self.tmpdir, "corrupt.jpg")
        with open(path, "wb") as f:
            f.write(b"this is not an image")
        result = self.det.detect(path)
        self.assertEqual(result["status"], STATUS_FRAME_FAILED)
        self.assertEqual(result["error"]["code"], "IMAGE_DECODE_FAILED")


class TestMBODetectorResults(unittest.TestCase):
    """탐지 결과 구조 및 집계 검증."""

    def test_result_structure_keys(self):
        """결과 dict 에 필수 키가 모두 있는지 확인"""
        det = make_detector(detections=[])
        result = det.detect(make_bgr_frame())
        expected_keys = {
            "status", "error", "warnings", "timestamp", "point_id",
            "model", "image", "inference_ms", "total_count",
            "counts", "confidence", "detections",
        }
        self.assertTrue(expected_keys.issubset(result.keys()))

    def test_counts_per_class(self):
        """클래스별 개체수 집계 확인"""
        det = make_detector(detections=[
            (3, 0.90, [10, 20, 100, 200]),   # starfish
            (3, 0.80, [110, 20, 200, 200]),  # starfish
            (2, 0.70, [210, 20, 300, 200]),  # scallop
            (0, 0.60, [310, 20, 400, 200]),  # holothurian
        ])
        result = det.detect(make_bgr_frame())
        self.assertEqual(result["counts"]["starfish"], 2)
        self.assertEqual(result["counts"]["scallop"], 1)
        self.assertEqual(result["counts"]["holothurian"], 1)
        self.assertEqual(result["counts"]["echinus"], 0)
        self.assertEqual(result["total_count"], 4)

    def test_confidence_statistics(self):
        """클래스별 신뢰도 통계(max, mean) 확인"""
        det = make_detector(detections=[
            (3, 0.90, [10, 20, 100, 200]),
            (3, 0.80, [110, 20, 200, 200]),
        ])
        result = det.detect(make_bgr_frame())
        star_conf = result["confidence"]["starfish"]
        self.assertAlmostEqual(star_conf["max"], 0.90, places=2)
        self.assertAlmostEqual(star_conf["mean"], 0.85, places=2)
        # 미검출 클래스의 신뢰도는 None
        self.assertIsNone(result["confidence"]["echinus"]["max"])
        self.assertIsNone(result["confidence"]["echinus"]["mean"])

    def test_detections_sorted_by_confidence(self):
        """탐지 결과가 confidence 내림차순으로 정렬되는지 확인"""
        det = make_detector(detections=[
            (0, 0.30, [10, 20, 100, 200]),
            (3, 0.95, [110, 20, 200, 200]),
            (2, 0.60, [210, 20, 300, 200]),
        ])
        result = det.detect(make_bgr_frame())
        confs = [d["confidence"] for d in result["detections"]]
        self.assertEqual(confs, sorted(confs, reverse=True))

    def test_point_id_propagated(self):
        """point_id 가 결과에 전달되는지 확인"""
        det = make_detector()
        result = det.detect(make_bgr_frame(), point_id="P1_MAIN")
        self.assertEqual(result["point_id"], "P1_MAIN")

    def test_point_id_none(self):
        """point_id 생략 시 None"""
        det = make_detector()
        result = det.detect(make_bgr_frame())
        self.assertIsNone(result["point_id"])

    def test_timestamp_format(self):
        """timestamp 가 ISO 형식인지 확인"""
        det = make_detector()
        result = det.detect(make_bgr_frame())
        from datetime import datetime
        # isoformat 으로 파싱 가능해야 한다
        datetime.fromisoformat(result["timestamp"])

    def test_model_info_in_result(self):
        """모델 설정이 결과에 포함되는지 확인"""
        det = make_detector()
        result = det.detect(make_bgr_frame())
        self.assertEqual(result["model"]["conf"], 0.25)
        self.assertEqual(result["model"]["iou"], 0.7)
        self.assertEqual(result["model"]["imgsz"], 640)

    def test_image_dimensions(self):
        """이미지 크기가 결과에 기록되는지 확인"""
        det = make_detector()
        result = det.detect(make_bgr_frame(width=320, height=240))
        self.assertEqual(result["image"]["width"], 320)
        self.assertEqual(result["image"]["height"], 240)


class TestMBODetectorConversion(unittest.TestCase):
    """to_observation() 및 to_flat_row() 변환 함수 검증."""

    def _make_ok_result(self, starfish_count=2, scallop_count=1):
        det = make_detector(detections=(
            [(3, 0.90, [10, 20, 100, 200])] * starfish_count +
            [(2, 0.70, [210, 20, 300, 200])] * scallop_count
        ))
        return det.detect(make_bgr_frame())

    def test_to_observation_ok(self):
        """OK 결과 → starfish/shell count 와 confidence"""
        result = self._make_ok_result()
        obs = to_observation(result)
        self.assertEqual(obs["starfish_count"], 2)
        self.assertEqual(obs["shell_count"], 1)
        self.assertIsInstance(obs["starfish_confidence"], float)
        self.assertIsInstance(obs["shell_confidence"], float)

    def test_to_observation_zero_detections(self):
        """탐지 0개 OK → count=0, confidence=0.0"""
        result = self._make_ok_result(starfish_count=0, scallop_count=0)
        obs = to_observation(result)
        self.assertEqual(obs["starfish_count"], 0)
        self.assertEqual(obs["starfish_confidence"], 0.0)
        self.assertEqual(obs["shell_count"], 0)
        self.assertEqual(obs["shell_confidence"], 0.0)

    def test_to_observation_frame_failed(self):
        """FRAME_FAILED → 4개 값 전부 None"""
        det = make_detector()
        result = det.detect(None)
        obs = to_observation(result)
        self.assertIsNone(obs["starfish_count"])
        self.assertIsNone(obs["starfish_confidence"])
        self.assertIsNone(obs["shell_count"])
        self.assertIsNone(obs["shell_confidence"])

    def test_to_observation_inference_failed(self):
        """INFERENCE_FAILED → 4개 값 전부 None"""
        det = make_detector(raise_on_predict=True)
        result = det.detect(make_bgr_frame())
        obs = to_observation(result)
        self.assertIsNone(obs["starfish_count"])

    def test_to_flat_row_ok(self):
        """OK 결과 → flat dict 에 필수 필드 존재"""
        result = self._make_ok_result()
        row = to_flat_row(result)
        self.assertEqual(row["status"], STATUS_OK)
        self.assertIsNone(row["error_code"])
        self.assertIsNotNone(row["timestamp"])
        self.assertEqual(row["total_count"], 3)
        self.assertEqual(row["starfish_count"], 2)
        self.assertEqual(row["scallop_count"], 1)
        # detections_json 은 유효한 JSON 이어야 한다
        parsed = json.loads(row["detections_json"])
        self.assertEqual(len(parsed), 3)

    def test_to_flat_row_frame_failed(self):
        """FRAME_FAILED → status, error_code 기록, counts 는 None"""
        det = make_detector()
        result = det.detect(None)
        row = to_flat_row(result)
        self.assertEqual(row["status"], STATUS_FRAME_FAILED)
        self.assertEqual(row["error_code"], "FRAME_NONE")
        self.assertIsNone(row["total_count"])
        self.assertIsNone(row["starfish_count"])


class TestMBODetectorSaveImages(unittest.TestCase):
    """이미지 저장 기능 검증."""

    def test_save_images_creates_files(self):
        """save_images=True → 어노테이션 이미지 저장"""
        tmpdir = tempfile.mkdtemp()
        try:
            det = make_detector(
                detections=[(3, 0.85, [10, 20, 100, 200])],
                save_images=True,
                save_dir=tmpdir,
            )
            result = det.detect(make_bgr_frame())
            self.assertEqual(result["status"], STATUS_OK)
            # annotated 이미지가 저장되었는지 확인
            self.assertIsNotNone(result["image"]["annotated_image_path"])
            self.assertTrue(os.path.isfile(result["image"]["annotated_image_path"]))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_save_images_false_no_files(self):
        """save_images=False → 파일 저장 안 함"""
        det = make_detector(save_images=False)
        result = det.detect(make_bgr_frame())
        self.assertIsNone(result["image"]["annotated_image_path"])


class TestMBODetectorBlankCheck(unittest.TestCase):
    """blank_check 옵션 검증."""

    def test_blank_check_disabled(self):
        """blank_check=False → 단색 프레임도 추론 시도"""
        det = make_detector(blank_check=False)
        black = np.zeros((480, 640, 3), dtype=np.uint8)
        result = det.detect(black)
        # blank_check 꺼져 있으므로 FRAME_FAILED 가 아닌 OK
        self.assertEqual(result["status"], STATUS_OK)


if __name__ == "__main__":
    unittest.main()
