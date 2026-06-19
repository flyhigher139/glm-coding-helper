from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import math
import os
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageFont


ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = ROOT.parents[1]


def find_image(name: str, dataset_root: Path) -> Path | None:
    candidates = [
        dataset_root / "auto_captured" / name,
        dataset_root / "auto_captured_archive" / "captured_310_20260513_042005" / name,
        dataset_root / "auto_captured_autolabel" / "images" / name,
        dataset_root / "char_detector_yolo" / "images" / "train" / name,
        dataset_root / "char_detector_yolo" / "images" / "val" / name,
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def point_for_prompt(prompt: str, box_chars: list[str], boxes: list[list[float]]) -> list[dict]:
    used: set[int] = set()
    out: list[dict] = []
    for ch in prompt:
        found = None
        for idx, box_ch in enumerate(box_chars):
            if idx not in used and box_ch == ch:
                found = idx
                break
        if found is None:
            raise ValueError(f"cannot map prompt={prompt!r} box_chars={box_chars!r}")
        used.add(found)
        x1, y1, x2, y2 = boxes[found]
        out.append({"x": (x1 + x2) / 2.0, "y": (y1 + y2) / 2.0, "char": ch})
    return out


def points_ok(pred: list[dict], gt: list[dict], threshold: float) -> tuple[bool, float]:
    if len(pred) != len(gt):
        return False, float("inf")
    max_dist = 0.0
    for p, g in zip(pred, gt):
        d = math.hypot(float(p["x"]) - float(g["x"]), float(p["y"]) - float(g["y"]))
        max_dist = max(max_dist, d)
        if d > threshold:
            return False, max_dist
    return True, max_dist


def scan_windows_fonts() -> list[tuple[str, int]]:
    if os.name == "nt":
        font_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    else:
        # On macOS / Linux, MS fonts are not available; fall back to
        # /Library/Fonts. Most font lookups below will simply return None
        # for these filenames on a non-Windows host, which is fine — this
        # is a dev/eval tool.
        font_dir = Path("/Library/Fonts")
    names = [
        "simsun.ttc",
        "simhei.ttf",
        "simkai.ttf",
        "simfang.ttf",
        "msyh.ttc",
        "msyhbd.ttc",
        "msyhl.ttc",
        "Deng.ttf",
        "Dengb.ttf",
        "Dengl.ttf",
    ]
    fonts: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for name in names:
        path = font_dir / name
        if not path.exists():
            continue
        for idx in range(8):
            try:
                font = ImageFont.truetype(str(path), 40, index=idx)
                cn = font.getbbox("测")
                en = font.getbbox("A")
            except Exception:
                break
            cn_w = cn[2] - cn[0]
            en_w = en[2] - en[0]
            if cn_w >= 25 and cn_w >= en_w * 1.2 and (str(path), idx) not in seen:
                fonts.append((str(path), idx))
                seen.add((str(path), idx))
    return fonts


def load_grabber(reference_root: Path):
    server_path = reference_root / "captcha" / "ddddocr_server.py"
    spec = importlib.util.spec_from_file_location("grabber_ddddocr_server", server_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {server_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    logging.getLogger("ddddocr-server").disabled = True
    module._all_font_paths[:] = scan_windows_fonts()
    module._variant_cache.clear()
    module._font_obj_cache.clear()
    return module


def start_our_worker(mode: str) -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["CNCAPTCHA_OCR_MODE"] = mode
    env.setdefault("CNCAPTCHA_YOLO_DEVICE", "cpu")
    _py_bin = "Scripts" if os.name == "nt" else "bin"
    _py_exe = "python.exe" if os.name == "nt" else "python"
    py = ROOT / ".venv_paddle" / _py_bin / _py_exe
    if not py.exists():
        py = Path(sys.executable)
    return subprocess.Popen(
        [str(py), "-u", str(ROOT / "scripts" / "tools" / "captcha_worker.py")],
        cwd=str(ROOT),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )


def ask_our_worker(proc: subprocess.Popen, image_path: Path, prompt: str, timeout: float = 45.0) -> dict:
    assert proc.stdin is not None and proc.stdout is not None
    payload = json.dumps({"image_path": str(image_path), "chars": list(prompt)}, ensure_ascii=False) + "\n"
    proc.stdin.write(payload.encode("utf-8"))
    proc.stdin.flush()
    start = time.perf_counter()
    while time.perf_counter() - start < timeout:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("our worker exited")
        text = line.decode("utf-8", errors="replace").strip()
        if not text.startswith("{"):
            continue
        return json.loads(text)
    raise TimeoutError("our worker timeout")


def run(args: argparse.Namespace) -> int:
    dataset_root = Path(args.dataset_root).resolve()
    labels = json.loads((dataset_root / "glm_ocr_labels_all.json").read_text(encoding="utf-8"))
    items = []
    for name, row in labels.items():
        if row.get("has_error"):
            continue
        image = find_image(name, dataset_root)
        if image is None:
            continue
        prompt = str(row["prompt"])
        box_chars = list(row["box_chars"])
        boxes = list(row["boxes"])
        if len(prompt) != 3 or len(box_chars) != 3 or len(boxes) != 3:
            continue
        try:
            gt = point_for_prompt(prompt, box_chars, boxes)
        except Exception:
            continue
        items.append({"name": name, "image": image, "prompt": prompt, "gt": gt})
    if args.limit:
        items = items[: args.limit]

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    threshold = float(args.threshold)
    summary = {"items": len(items), "threshold": threshold, "runs": {}}

    if args.engine in {"grabber", "both"}:
        grabber = load_grabber(Path(args.reference_root).resolve())
        rows = []
        ok_count = 0
        times = []
        for idx, item in enumerate(items, 1):
            t0 = time.perf_counter()
            try:
                pred = grabber.solve_click_captcha(item["image"].read_bytes(), item["prompt"])
                success, max_dist = points_ok(pred, item["gt"], threshold)
                err = ""
            except Exception as exc:
                pred = []
                success = False
                max_dist = float("inf")
                err = str(exc)
            ms = (time.perf_counter() - t0) * 1000
            times.append(ms)
            ok_count += int(success)
            rows.append({"name": item["name"], "ok": success, "max_dist": max_dist, "ms": round(ms, 1), "error": err})
            if idx % 25 == 0:
                print(f"grabber {idx}/{len(items)} ok={ok_count}", flush=True)
        summary["runs"]["grabber_winfonts"] = {
            "ok": ok_count,
            "total": len(items),
            "acc": ok_count / max(len(items), 1),
            "avg_ms": sum(times) / max(len(times), 1),
            "p50_ms": sorted(times)[len(times) // 2] if times else 0,
            "fonts": len(getattr(grabber, "_all_font_paths", [])),
        }
        (out_dir / "grabber_winfonts_rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.engine in {"our", "both"}:
        proc = start_our_worker(args.our_mode)
        rows = []
        ok_count = 0
        times = []
        try:
            for idx, item in enumerate(items, 1):
                t0 = time.perf_counter()
                try:
                    resp = ask_our_worker(proc, item["image"], item["prompt"])
                except Exception as exc:
                    resp = {"success": False, "error": str(exc)}
                if resp.get("success"):
                    img = Image.open(item["image"])
                    pred = [{"x": float(c["nx"]) * img.width, "y": float(c["ny"]) * img.height} for c in resp.get("click_coords", [])]
                    success, max_dist = points_ok(pred, item["gt"], threshold)
                    err = ""
                    ms = float(resp.get("elapsed_ms") or ((time.perf_counter() - t0) * 1000))
                else:
                    success = False
                    max_dist = float("inf")
                    err = str(resp.get("error", "failed"))
                    ms = (time.perf_counter() - t0) * 1000
                times.append(ms)
                ok_count += int(success)
                rows.append({"name": item["name"], "ok": success, "max_dist": max_dist, "ms": round(ms, 1), "error": err, "resp": resp})
                if idx % 25 == 0:
                    print(f"our {idx}/{len(items)} ok={ok_count}", flush=True)
        finally:
            try:
                proc.kill()
            except Exception:
                pass
        summary["runs"][f"our_{args.our_mode}"] = {
            "ok": ok_count,
            "total": len(items),
            "acc": ok_count / max(len(items), 1),
            "avg_ms": sum(times) / max(len(times), 1),
            "p50_ms": sorted(times)[len(times) // 2] if times else 0,
        }
        (out_dir / f"our_{args.our_mode}_rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", default=str(PROJECT_ROOT / "dataset"))
    parser.add_argument("--reference-root", default=str(PROJECT_ROOT / "_reference" / "glm-coding-grabber"))
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "dataset" / "extreme_compare"))
    parser.add_argument("--engine", choices=["grabber", "our", "both"], default="both")
    parser.add_argument("--our-mode", default="cpu")
    parser.add_argument("--threshold", type=float, default=35.0)
    parser.add_argument("--limit", type=int, default=0)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
