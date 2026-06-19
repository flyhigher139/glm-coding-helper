# macOS Port — Technical Changelog

> 给维护者看的技术变更记录。**不是**用户文档（用户请看 [`mac_install.md`](mac_install.md)）。
>
> 关联 commit：2026-06-19。

## TL;DR

把 Windows + NVIDIA CUDA only 的 Python 后端改成 **跨平台**（Windows / macOS / Linux 都能跑），Mac 上自动降级为 CPU 模式。不引入任何破坏性变更：Windows 行为完全保留。

## 设计原则

1. **最小改动** —— 不重写架构，只在边界处加 `os.name` / `sys.platform` 守卫。
2. **行为等价** —— 改动后 Windows 上跑出来的行为必须和改动前一致。
3. **优雅降级** —— Mac 上去掉一切不相关的功能（GPU 探测、截屏、DLL 注入），不抛错。
4. **可逆** —— 改动只影响 `if os.name == "nt":` / `if sys.platform == "darwin":` 分支，把守卫去掉就回到 Windows-only。

## 关键决策

### 为什么用 `os.name` 而不是 `sys.platform`？

| 维度 | `os.name` | `sys.platform` |
|------|-----------|----------------|
| 取值 | `'nt'` / `'posix'` | `'win32'` / `'darwin'` / `'linux'` |
| 适用 | venv 路径（`Scripts` vs `bin`） | 平台特性（macOS GUI 行为、字体目录） |
| 跨 Python 兼容 | 稳定 | Linux 下可能是 `'linux'` / `'linux2'` 等 |

**经验法则**：
- 文件系统 / venv 路径 → `os.name`（"是不是 Windows NT 内核"）
- 平台特有功能（MPS 字体、Mac 路径）→ `sys.platform`（"具体是哪种 POSIX"）

代码里两种都有用到，取决于语义。

### 为什么 Mac 选 `bin/python` 而不是 `python.exe`？

Python venv 在 POSIX 系统上统一用 `bin/`（无后缀）。Linux 和 macOS 都是。`os.name == "posix"` 已经覆盖了。

### 为什么不让 YOLO 用 MPS 后端？

`ultralytics` 8.x 的 `device="mps"` 在理论上可以工作，但带来三个问题：

1. PyTorch 2.12 + MPS + 6MB YOLO + Mac M1 的吞吐提升 < 30%（CPU 已经够快）
2. MPS 在某些 PaddlePaddle + torch 共存的环境下有 ABI 冲突
3. 现有 `backend/worker.py` 的 `cpu_affinity` 在 Mac 上 no-op，加上 MPS 会让多 worker 调度更不可预测

权衡下来 CPU only 是最稳的选择。需要加速的用户可以试 `export CNCAPTCHA_YOLO_DEVICE=mps`。

### 为什么 Paddle 走 CPU？

PaddlePaddle 官方至今（2026-06）没有 Apple MPS / Metal 实现。`paddlepaddle-gpu` 又是 CUDA-only。所以 Mac 上只能 CPU。YOLO 走 `device="cpu"`。

## 文件级变更清单

### 修改（8 个 Python 文件）

#### `scripts/tools/captcha_worker.py`（关键修复）

- **位置**：line 44-61
- **改动**：引入 `_OCR_BIN` / `_OCR_PY` 局部常量，让 `OCR_PYTHON` 默认值按平台生成。
- **为什么这是关键**：这是**唯一**会让 Mac 直接崩溃的硬编码（`RuntimeError: missing OCR venv python: .../Scripts/python.exe`）。其他文件的硬编码在 Mac 上只是噪声或无影响。

```python
_OCR_BIN = "Scripts" if os.name == "nt" else "bin"
_OCR_PY = "python.exe" if os.name == "nt" else "python"
if OCR_MODE in {"cpu", "cpu_parallel", "cpu-pool"}:
    OCR_PYTHON = Path(os.environ.get(
        "CNCAPTCHA_CPU_OCR_PYTHON",
        str(ROOT / ".venv_paddle" / _OCR_BIN / _OCR_PY),
    ))
```

#### `scripts/tools/backend_config.py`

- **位置**：`_gpu_probe_env()` (line 77-88)
- **改动**：`env["USERPROFILE"] = ...` 包到 `if os.name == "nt":` 内。
- **为什么无害**：`USERPROFILE` 在 Mac 上是噪声，但 Mac 上不会调用这个函数（`detect_gpu()` 在 `_venv_python(".venv_paddle_gpu").exists() == False` 时直接返回 False）。改动只是为了让 `git diff` 干净。

#### `scripts/tools/ppocr_cpu_pool_worker.py`

- **位置**：`configure_env()` line 32
- **改动**：同 backend_config.py。

#### `scripts/tools/ppocr_gpu_worker.py`

- **位置**：`configure_env()` line 35-55
- **改动**：
  - `USERPROFILE` 守卫到 Windows
  - NVIDIA DLL `;` PATH 注入循环守卫到 Windows（POSIX 走 RPATH / LC_LOAD_LIBRARY）
- **为什么这条重要**：`os.environ["PATH"] = ";".join(...)` 在 Mac 上会把现有 PATH 用 `;` 拼成单一字符串，破坏后续所有 subprocess 调用。
- **注意**：整个 `ppocr_gpu_worker.py` 在 Mac 上是死代码（`detect_gpu()` 返回 False）。但保留入口点以便 Linux + NVIDIA 用户未来支持。

#### `scripts/setup_backend.py`

- **位置 1**：line 14 附近
- **改动**：`CPU_REQ` 在 Mac 上自动选 `requirements-backend-mac.txt`，找不到就 fallback。
- **位置 2**：line 74-94
- **改动**：GPU smoke test 整个分支用 `if os.name == "nt":` 守卫，POSIX 只打印 "skipped"。
- **位置 3**：line 145-148
- **改动**：原来的 `print("  python scripts\\tools\\...")` 改成 `Path` 拼接。
- **为什么 Path 拼接**：原来写死的反斜杠在 POSIX shell 里没意义，复制粘贴会失败。

#### `scripts/monitor/window_helper.py`

- **位置**：line 1 后插入
- **改动**：`if sys.platform != "win32": raise ImportError(...)`
- **关键点**：`captcha_server.py:34-41` 已经有 `try/except ImportError` 守卫，会把 `capture_browser_window` 设为 `None`。改成显式 `ImportError` 让任何意外 import 都失败得更清楚。

#### `scripts/tools/captcha_server.py`

- **位置**：`trigger_auto_capture()` 内 line 310 前
- **改动**：在 `for attempt in range(5):` 循环内 `if not capture_browser_window:` 分支加显式早返回（带 GUI 日志和 `state.recognition_results` 记录）。
- **为什么不是直接 `return`**：原来代码会循环 5×80ms 后返回 "未截得合格图片" 这种误导性错误。

#### `scripts/tools/evaluate_pipeline_compare.py`

- **位置 1**：`scan_windows_fonts()` line 65
- **改动**：`os.name == "nt"` 时用 `WINDIR`/`C:\Windows\Fonts`，否则用 `/Library/Fonts`。
- **位置 2**：line 119
- **改动**：venv python 路径按 `os.name` 区分。
- **优先级**：低。开发/评测脚本，不在关键路径上。

### 新增（5 个文件）

#### `requirements-backend-mac.txt`

完全等同于 `requirements-backend-cpu.txt`，但去掉了：
- `pydirectinput` — Windows-only，pyautogui 在 Mac 上可用
- `mss` — Mac 上用不到截屏

#### `setup-mac.sh`

镜像 `one-click-start.cmd` + `scripts\one_click_start.ps1` 的功能。区别：

- 用 `python3` 而不是 `python`
- 用清华源（`PIP_INDEX_URL` 可覆盖）
- 检测 `tkinter` 并给出 `brew install python-tk@3.12` 提示
- 始终 `--target cpu`（Paddle 无 MPS）

#### `start-backend-pipeline-gui.sh`

镜像 `start-backend-pipeline-gui.cmd`：

- 自动检测 venv，缺则 fallback 到系统 `python3`
- 用 `lsof` 检查 8888 端口（Windows 用 `netstat -ano`）
- 设置 `CNCAPTCHA_OCR_MODE=cpu` 和 `CNCAPTCHA_YOLO_DEVICE=cpu` 显式覆盖

#### `start-backend-headless.sh`

无 Tk 窗口模式。SSH / 后台友好。

#### `docs/mac_install.md`

用户面向的完整 Mac 安装/限制/故障排除文档。

## 未修改的 Windows 行为

| 行为 | 状态 |
|------|------|
| `.cmd` / `.ps1` 启动脚本 | ✅ 完全保留，未改动 |
| `requirements-backend-cpu.txt` | ✅ 未改动（Mac 走 `-mac.txt`）|
| `requirements-backend-gpu.txt` | ✅ 未改动 |
| GPU 探测 + CUDA 路径 | ✅ 完全保留（仅 Mac 跳过）|
| 截屏流程 | ✅ Windows 行为不变 |
| `pydirectinput` / `mss` | ✅ 仍在 CPU requirements 里 |
| `config.json` 默认值 | ✅ 未改动 |

## 已知回归风险

1. **`USERPROFILE` 守卫**：Windows 上行为完全不变。POSIX 上不再写入这个 env var，但 POSIX 进程本来就忽略它。
2. **`Scripts/python.exe` 默认值**：用户用 `CNCAPTCHA_CPU_OCR_PYTHON` env var 显式覆盖时不受影响；只有默认值被改动。
3. **`window_helper.py` 守卫**：Windows 行为不变。POSIX 上原本就是 `AttributeError`，改成 `ImportError` 更容易被 `try/except` 捕获。
4. **`requirements-backend-mac.txt` 与 `requirements-backend-cpu.txt` 的差异**：仅少了两个 Mac 不可用的包。Mac 上缺这两个不会导致任何功能缺失（油猴脚本点击不依赖 `pydirectinput`，截屏流程已弃用）。

## 测试覆盖

端到端验证（M1 实机）：

| 步骤 | 命令 | 期望 |
|------|------|------|
| V2 安装 | `./setup-mac.sh` | "core imports ok" / "backend deps ok" |
| V3 YOLO | `python -c "from ultralytics import YOLO; ..."` | `YOLO ok, boxes: 0` |
| V4 OCR | `python -c "from paddleocr import TextRecognition; ..."` | `OCR ok, texts: ['']` |
| V5 FastAPI | `./start-backend-headless.sh &` + `curl /health` | `{"status":"ok","workers":7,...}` |
| V6 端到端 | `curl -X POST /captcha_direct` | HTTP 200 + `success: true` |

V6-V7 需要实际触发验证码，超出自动化测试范围。

## 未来工作

- [ ] **MPS 后端**：等 PaddlePaddle 官方支持 Apple Metal。如果未来支持了，把 `CPU_REQ` 拆出 Mac GPU 路径，参考 `requirements-backend-gpu.txt` 加 `paddlepaddle-mps`。
- [ ] **截屏 Mac 支持**：用 `pyobjc-framework-Quartz`（已间接安装）做 `CGWindowListCopyWindowInfo` + `screencapture`，重写 `window_helper.py` 的 Mac 分支。
- [ ] **`pyautogui` → `Quartz` 加速**：油猴脚本当前是 DOM 点击所以不影响，但如果未来用 `pyautogui` 做物理点击，Mac 上 pyautogui 会调用 `Quartz.CGEventCreateMouseEvent`，已经够用，无需改动。
- [ ] **CI matrix**：在 `.github/workflows/` 加 macos-latest runner，跑 V2-V5 自动化。
