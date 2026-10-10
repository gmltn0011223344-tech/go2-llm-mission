"""
vision/mbo_detector.py
MBO-YOLO 해양생물 탐지 모듈 (독립 실행 가능)

※ 기존 vision/detector.py (MarineDetector) 는 건드리지 않는다. 이 파일은 그 옆에 추가만 한다.

빠른 사용법
    from vision.mbo_detector import MBODetector, to_observation

    det = MBODetector()                       # model/mbo_final.pt 를 자동으로 찾는다
    result = det.detect(image, point_id="P1_MAIN")   # image: 경로 / ndarray(BGR) / JPEG bytes
    if result["status"] == "OK":
        save_observation(point_id=..., robot_x=..., ..., **to_observation(result))

역할
    사진 1장(파일 경로 / OpenCV ndarray / JPEG bytes)을 받아서
    MBO-YOLO로 탐지하고, 결과를 "정해진 형태의 dict"로 돌려준다.
    DB 저장, 로봇 이동, LLM 판단은 여기서 하지 않는다.

주의 (환경)
    - 반드시 MBO-YOLO 저장소의 커스텀 Ultralytics 8.3.56 환경에서 실행한다.
      (commit 001d65cc0d331e72cc47246e51f5e957dcfd8d27)
    - `pip install -U ultralytics` 를 하면 Addmodules 가 사라져 모델이 로드되지 않는다.
    - ndarray 를 넣을 때는 OpenCV 기본인 BGR 순서여야 한다. (RGB 면 색이 뒤집혀 탐지가 나빠진다)

상태(status) 3가지
    OK                : 추론까지 정상. 탐지 0개여도 OK 다. (counts 가 전부 0)
    FRAME_FAILED      : 사진 자체를 못 얻음. (counts 가 전부 None)
    INFERENCE_FAILED  : 사진은 정상인데 모델 로드/추론이 실패. (counts 가 전부 None)

    즉 "0" 은 '봤는데 없었다', "None" 은 '보지 못했다' 라는 뜻이다.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any, Optional

import cv2
import numpy as np

# ---------------------------------------------------------------- 고정값
# 학습 때 쓴 클래스 순서. 바꾸면 안 된다.
CLASS_NAMES = {0: "holothurian", 1: "echinus", 2: "scallop", 3: "starfish"}
CLASS_NAMES_KO = {
    "holothurian": "해삼",
    "echinus": "성게",
    "scallop": "가리비",
    "starfish": "불가사리",
}

DEFAULT_CONF = 0.25   # 운영용 기준. (0.001 은 성능 평가 전용이므로 여기서 쓰지 않는다)
DEFAULT_IOU = 0.7
DEFAULT_IMGSZ = 640
EXPECTED_ULTRALYTICS = "8.3.56"

# 가중치 기본 위치: <프로젝트>/model/mbo_final.pt → 없으면 <프로젝트>/mbo_final.pt
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_weights() -> str:
    for cand in (os.path.join(_BASE_DIR, "model", "mbo_final.pt"),
                 os.path.join(_BASE_DIR, "mbo_final.pt")):
        if os.path.isfile(cand):
            return cand
    return os.path.join(_BASE_DIR, "model", "mbo_final.pt")


STATUS_OK = "OK"
STATUS_FRAME_FAILED = "FRAME_FAILED"
STATUS_INFERENCE_FAILED = "INFERENCE_FAILED"

BOX_COLORS = {  # BGR
    "holothurian": (60, 180, 75),
    "echinus": (200, 130, 0),
    "scallop": (0, 165, 255),
    "starfish": (40, 40, 230),
}


class MBODetector:
    """
    사용 예
        det = MBODetector()                                    # 또는 MBODetector(weights="경로/mbo_final.pt")
        result = det.detect("test.jpg", point_id="P1_MAIN")   # 경로
        result = det.detect(frame, point_id="P1_MAIN")        # OpenCV ndarray (BGR)
    """

    def __init__(
        self,
        weights: Optional[str] = None,   # None 이면 default_weights() 위치를 쓴다
        conf: float = DEFAULT_CONF,
        iou: float = DEFAULT_IOU,
        imgsz: int = DEFAULT_IMGSZ,
        save_dir: str = "vision_outputs",
        save_images: bool = True,
        device: Optional[str] = None,   # None 이면 Ultralytics 가 알아서 고른다 ("cpu", "mps", "0" 등)
        blank_check: bool = True,       # 완전히 단색인 프레임(검은 화면 등)을 FRAME_FAILED 로 처리
        model: Any = None,              # 테스트용. 이미 만들어진 모델 객체를 직접 넣을 수 있다.
    ):
        self.weights = os.fspath(weights) if weights is not None else default_weights()
        self.conf = float(conf)
        self.iou = float(iou)
        self.imgsz = int(imgsz)
        self.save_dir = save_dir
        self.save_images = save_images
        self.device = device
        self.blank_check = blank_check
        self._model = model
        self._ultralytics_version: Optional[str] = None

    # ------------------------------------------------------------ 모델 로드
    def _load_model(self):
        """처음 detect() 할 때 한 번만 모델을 올린다."""
        if self._model is not None:
            return self._model

        if not os.path.isfile(self.weights):
            raise FileNotFoundError(f"가중치 파일이 없습니다: {self.weights}")

        import ultralytics
        from ultralytics import YOLO

        self._ultralytics_version = getattr(ultralytics, "__version__", None)
        model = YOLO(self.weights)

        # 클래스 순서가 학습 때와 같은지 확인한다. 다르면 개체수가 엉뚱한 종으로 세어진다.
        names = getattr(model, "names", None)
        if names:
            got = {int(k): str(v).lower() for k, v in dict(names).items()}
            if got != CLASS_NAMES:
                raise ValueError(f"클래스 순서가 다릅니다. 기대값 {CLASS_NAMES}, 모델 {got}")

        self._model = model
        return model

    # ------------------------------------------------------------ 입력 → 프레임
    def _to_frame(self, source):
        """
        입력을 BGR ndarray 로 바꾼다.
        반환: (frame, source_type, original_path, (error_code, message) 또는 None)
        """
        if source is None:
            return None, "none", None, ("FRAME_NONE", "입력이 None 입니다. 카메라 프레임을 받지 못했습니다.")

        # 1) 파일 경로
        if isinstance(source, (str, os.PathLike)):
            path = os.fspath(source)
            if not os.path.isfile(path):
                return None, "path", path, ("FILE_NOT_FOUND", f"파일이 없습니다: {path}")
            frame = cv2.imread(path, cv2.IMREAD_COLOR)
            if frame is None:
                return None, "path", path, ("IMAGE_DECODE_FAILED", f"이미지로 읽을 수 없습니다: {path}")
            src_type, src_path = "path", path

        # 2) JPEG/PNG bytes (WebRTC 나 HTTP 로 받은 압축 이미지)
        elif isinstance(source, (bytes, bytearray, memoryview)):
            buf = np.frombuffer(bytes(source), dtype=np.uint8)
            if buf.size == 0:
                return None, "bytes", None, ("FRAME_EMPTY", "bytes 길이가 0 입니다.")
            frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            if frame is None:
                return None, "bytes", None, ("IMAGE_DECODE_FAILED", "bytes 를 이미지로 디코딩할 수 없습니다.")
            src_type, src_path = "bytes", None

        # 3) OpenCV ndarray
        elif isinstance(source, np.ndarray):
            frame, src_type, src_path = source, "ndarray", None
            if frame.size == 0:
                return None, src_type, None, ("FRAME_EMPTY", "프레임 크기가 0 입니다.")
            if frame.ndim == 2:                                   # 흑백
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            elif frame.ndim == 3 and frame.shape[2] == 4:         # BGRA
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            elif not (frame.ndim == 3 and frame.shape[2] == 3):
                return None, src_type, None, ("FRAME_BAD_SHAPE", f"지원하지 않는 프레임 모양입니다: {source.shape}")
            if frame.dtype != np.uint8:
                return None, src_type, None, ("FRAME_BAD_DTYPE", f"uint8 이 아닙니다: {frame.dtype}")

        else:
            return None, type(source).__name__, None, (
                "FRAME_BAD_TYPE", f"지원하지 않는 입력 타입입니다: {type(source).__name__}")

        # 완전히 단색인 화면(검은 프레임 등)은 '사진을 못 얻은 것'으로 본다.
        if self.blank_check and float(frame.std()) < 1.0:
            return None, src_type, src_path, ("FRAME_BLANK", "프레임이 단색입니다. (검은 화면 등)")

        return np.ascontiguousarray(frame), src_type, src_path, None

    # ------------------------------------------------------------ 메인
    def detect(self, source, point_id: Optional[str] = None) -> dict:
        """사진 1장을 탐지하고 결과 dict 를 돌려준다. 예외를 밖으로 던지지 않는다."""
        now = datetime.now()
        result = self._empty_result(now, point_id)

        # 1) 프레임 확인
        frame, src_type, src_path, err = self._to_frame(source)
        result["image"]["source_type"] = src_type
        result["image"]["image_path"] = src_path
        if err is not None:
            result["status"] = STATUS_FRAME_FAILED
            result["error"] = {"code": err[0], "message": err[1]}
            return result

        h, w = frame.shape[:2]
        result["image"]["width"], result["image"]["height"] = int(w), int(h)

        # 원본 저장 (경로로 들어온 사진은 이미 파일이 있으므로 다시 저장하지 않는다)
        stem = now.strftime("%Y%m%d_%H%M%S_%f")[:-3] + (f"_{point_id}" if point_id else "")
        if self.save_images and src_path is None:
            result["image"]["image_path"] = self._save(frame, stem + "_raw.jpg", result)

        # 2) 모델 로드
        try:
            model = self._load_model()
        except Exception as e:  # noqa: BLE001
            result["status"] = STATUS_INFERENCE_FAILED
            result["error"] = {"code": "MODEL_LOAD_FAILED", "message": f"{type(e).__name__}: {e}"}
            return result

        result["model"]["ultralytics_version"] = self._ultralytics_version
        if self._ultralytics_version and self._ultralytics_version != EXPECTED_ULTRALYTICS:
            result["warnings"].append(
                f"Ultralytics 버전이 {self._ultralytics_version} 입니다. 학습 환경은 {EXPECTED_ULTRALYTICS} 입니다.")

        # 3) 추론
        try:
            kwargs = dict(source=frame, conf=self.conf, iou=self.iou, imgsz=self.imgsz, verbose=False)
            if self.device is not None:
                kwargs["device"] = self.device
            t0 = time.perf_counter()
            preds = model.predict(**kwargs)
            result["inference_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
            detections = self._parse(preds)
        except Exception as e:  # noqa: BLE001
            result["status"] = STATUS_INFERENCE_FAILED
            result["error"] = {"code": "PREDICT_FAILED", "message": f"{type(e).__name__}: {e}"}
            return result

        # 4) 집계
        result["status"] = STATUS_OK
        result["detections"] = detections
        result["total_count"] = len(detections)
        for name in CLASS_NAMES.values():
            values = sorted((d["confidence"] for d in detections if d["class_name"] == name), reverse=True)
            result["counts"][name] = len(values)
            result["confidence"][name] = {
                "max": values[0] if values else None,
                "mean": round(sum(values) / len(values), 4) if values else None,
                "values": values,
            }

        # 5) 박스 그린 이미지 저장 (탐지 0개여도 저장한다. '봤는데 없었다'는 증거가 된다)
        if self.save_images:
            result["image"]["annotated_image_path"] = self._save(
                self._draw(frame, detections), stem + "_det.jpg", result)

        return result

    # ------------------------------------------------------------ 내부 도구
    def _empty_result(self, now: datetime, point_id: Optional[str]) -> dict:
        names = list(CLASS_NAMES.values())
        return {
            "status": None,
            "error": None,
            "warnings": [],
            "timestamp": now.isoformat(timespec="milliseconds"),
            "point_id": point_id,
            "model": {
                "weights": os.path.basename(self.weights),
                "conf": self.conf,
                "iou": self.iou,
                "imgsz": self.imgsz,
                "ultralytics_version": None,
            },
            "image": {
                "source_type": None,
                "width": None,
                "height": None,
                "image_path": None,
                "annotated_image_path": None,
            },
            "inference_ms": None,
            "total_count": None,
            "counts": {n: None for n in names},
            "confidence": {n: {"max": None, "mean": None, "values": None} for n in names},
            "detections": None,
        }

    @staticmethod
    def _to_numpy(x) -> np.ndarray:
        """torch.Tensor 든 ndarray 든 numpy 로 바꾼다."""
        if hasattr(x, "detach"):
            x = x.detach()
        if hasattr(x, "cpu"):
            x = x.cpu()
        if hasattr(x, "numpy"):
            x = x.numpy()
        return np.asarray(x)

    def _parse(self, preds) -> list:
        """Ultralytics 결과 → 개별 탐지 목록 (confidence 높은 순)"""
        if not preds:
            raise RuntimeError("모델이 결과를 돌려주지 않았습니다.")
        boxes = getattr(preds[0], "boxes", None)
        if boxes is None or len(boxes) == 0:
            return []

        cls = self._to_numpy(boxes.cls).astype(int).reshape(-1)
        conf = self._to_numpy(boxes.conf).astype(float).reshape(-1)
        xyxy = self._to_numpy(boxes.xyxy).astype(float).reshape(-1, 4)

        out = []
        for c, p, b in zip(cls, conf, xyxy):
            name = CLASS_NAMES.get(int(c))
            if name is None:
                raise ValueError(f"알 수 없는 클래스 번호입니다: {int(c)}")
            out.append({
                "class_id": int(c),
                "class_name": name,
                "confidence": round(float(p), 4),
                "bbox_xyxy": [round(float(v), 1) for v in b],   # [x1, y1, x2, y2] 픽셀
            })
        out.sort(key=lambda d: d["confidence"], reverse=True)
        return out

    @staticmethod
    def _draw(frame: np.ndarray, detections: list) -> np.ndarray:
        img = frame.copy()
        # 사진 크기에 맞춰 선 굵기와 글자 크기를 정한다. (4K 사진에서도 글자가 보이도록)
        longer = max(img.shape[:2])
        line = max(2, round(longer / 640))
        scale = max(0.5, longer / 1280 * 0.6)
        text_line = max(1, round(scale * 2))
        pad = max(3, round(scale * 6))
        for d in detections:
            x1, y1, x2, y2 = (int(round(v)) for v in d["bbox_xyxy"])
            color = BOX_COLORS[d["class_name"]]
            cv2.rectangle(img, (x1, y1), (x2, y2), color, line)
            label = f'{d["class_name"]} {d["confidence"]:.2f}'
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, text_line)
            ty = y1 - pad if y1 - th - 2 * pad > 0 else y1 + th + pad
            cv2.rectangle(img, (x1, ty - th - pad), (x1 + tw + 2 * pad, ty + pad), color, -1)
            cv2.putText(img, label, (x1 + pad, ty), cv2.FONT_HERSHEY_SIMPLEX, scale,
                        (255, 255, 255), text_line, cv2.LINE_AA)
        return img

    def _save(self, img: np.ndarray, filename: str, result: dict) -> Optional[str]:
        """이미지 저장. 저장에 실패해도 탐지 결과는 살린다."""
        try:
            os.makedirs(self.save_dir, exist_ok=True)
            path = os.path.join(self.save_dir, filename)
            if not cv2.imwrite(path, img):
                raise OSError("cv2.imwrite 가 False 를 돌려줬습니다.")
            return path
        except Exception as e:  # noqa: BLE001
            result["warnings"].append(f"이미지 저장 실패({filename}): {e}")
            return None


# ---------------------------------------------------------------- DB 용 변환
def to_observation(result: dict) -> dict:
    """
    detect() 결과를 memory/observation_memory.py 의 save_observation() 에 그대로 넣을 수 있는
    4개 값으로 바꾼다.  사용:  save_observation(..., **to_observation(result))

    - shell 은 가리비(scallop) 를 뜻한다. (DB 컬럼 이름이 shell_count 이므로 여기서 맞춘다)
    - confidence 는 그 종의 평균값이다. (기존 MarineDetector 와 같은 방식)
    - 탐지 0개면 count=0, confidence=0.0 이다. (기존 MarineDetector 와 같은 방식)
    - status 가 OK 가 아니면 네 값 모두 None 이다.
      현재 DB 는 count 가 NOT NULL 이라 None 을 저장할 수 없으므로,
      status 가 OK 일 때만 저장하거나 DB 에 상태 컬럼을 추가해야 한다.
    """
    if result.get("status") != STATUS_OK:
        return {"starfish_count": None, "starfish_confidence": None,
                "shell_count": None, "shell_confidence": None}

    def conf(name):
        mean = result["confidence"][name]["mean"]
        return round(mean, 3) if mean is not None else 0.0

    return {
        "starfish_count": result["counts"]["starfish"],
        "starfish_confidence": conf("starfish"),
        "shell_count": result["counts"]["scallop"],
        "shell_confidence": conf("scallop"),
    }


def to_flat_row(result: dict) -> dict:
    """
    detect() 결과를 SQLite 한 줄에 넣기 좋은 납작한 dict 로 바꾼다.
    (나중에 DB 컬럼을 늘릴 때 쓸 수 있는 전체 정보. 지금 DB 에는 to_observation() 을 쓴다)
    """
    row = {
        "status": result["status"],
        "error_code": result["error"]["code"] if result["error"] else None,
        "timestamp": result["timestamp"],
        "point_id": result["point_id"],
        "conf_threshold": result["model"]["conf"],
        "iou_threshold": result["model"]["iou"],
        "imgsz": result["model"]["imgsz"],
        "inference_ms": result["inference_ms"],
        "total_count": result["total_count"],
        "image_path": result["image"]["image_path"],
        "annotated_image_path": result["image"]["annotated_image_path"],
        "detections_json": (
            json.dumps(result["detections"], ensure_ascii=False) if result["detections"] is not None else None),
    }
    for name in CLASS_NAMES.values():
        row[f"{name}_count"] = result["counts"][name]
        row[f"{name}_conf_max"] = result["confidence"][name]["max"]
        row[f"{name}_conf_mean"] = result["confidence"][name]["mean"]
    return row


# ---------------------------------------------------------------- 터미널 실행
def _main():
    import argparse

    ap = argparse.ArgumentParser(description="MBO-YOLO 탐지 (사진 1장)")
    ap.add_argument("image", help="사진 경로")
    ap.add_argument("--weights", default=None, help="생략하면 model/mbo_final.pt")
    ap.add_argument("--conf", type=float, default=DEFAULT_CONF)
    ap.add_argument("--iou", type=float, default=DEFAULT_IOU)
    ap.add_argument("--imgsz", type=int, default=DEFAULT_IMGSZ)
    ap.add_argument("--save-dir", default="vision_outputs")
    ap.add_argument("--device", default=None)
    ap.add_argument("--point-id", default=None)
    ap.add_argument("--flat", action="store_true", help="DB 용 납작한 형태로 출력")
    ap.add_argument("--obs", action="store_true", help="save_observation() 용 4개 값만 출력")
    args = ap.parse_args()

    det = MBODetector(weights=args.weights, conf=args.conf, iou=args.iou, imgsz=args.imgsz,
                      save_dir=args.save_dir, device=args.device)
    res = det.detect(args.image, point_id=args.point_id)
    out = to_observation(res) if args.obs else to_flat_row(res) if args.flat else res
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
