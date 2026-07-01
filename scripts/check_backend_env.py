from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIN_VERSIONS = {
    "paddleocr": (3, 7, 0),
    "paddlex": (3, 7, 0),
}
DEFAULT_OCR_MODEL = "PP-OCRv6_tiny_rec"


def _version_tuple(package_name: str) -> tuple[int, ...]:
    version = metadata.version(package_name)
    parts: list[int] = []
    for item in version.split("."):
        digits = "".join(ch for ch in item if ch.isdigit())
        parts.append(int(digits or "0"))
    return tuple(parts)


def _load_config() -> dict:
    config_path = ROOT / "config.json"
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _resolve_ocr_model() -> str:
    config = _load_config()
    return (
        os.environ.get("CNCAPTCHA_CPU_OCR_MODEL")
        or os.environ.get("GLM_OCR_MODEL")
        or str(config.get("ocr_model", DEFAULT_OCR_MODEL))
    ).strip() or DEFAULT_OCR_MODEL


def check_backend_env(check_tk: bool = False) -> None:
    if check_tk:
        import tkinter  # noqa: F401

    import cv2  # noqa: F401
    import fastapi  # noqa: F401
    import numpy  # noqa: F401
    import paddle  # noqa: F401
    import paddleocr  # noqa: F401
    import paddlex  # noqa: F401
    import PIL  # noqa: F401
    import psutil  # noqa: F401
    import ultralytics  # noqa: F401
    import uvicorn  # noqa: F401

    for package_name, minimum in MIN_VERSIONS.items():
        current = _version_tuple(package_name)
        if current < minimum:
            raise RuntimeError(
                f"{package_name} is too old: installed {metadata.version(package_name)}, "
                f"required >= {'.'.join(str(part) for part in minimum)}"
            )

    model_name = _resolve_ocr_model()
    from paddlex.inference.models.bindings.registry import default_registry

    default_registry.get_binding(model_name, "paddle_dynamic")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-tk", action="store_true")
    args = parser.parse_args(argv)
    try:
        check_backend_env(check_tk=args.check_tk)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
