# macOS 安装说明（Apple Silicon / Intel）

本项目原本只支持 Windows + NVIDIA GPU。Mac 版本以 **CPU-only 模式** 跑通，油猴脚本照常工作。

## 系统要求

- macOS 12+（Apple Silicon M1/M2/M3 或 Intel）
- Homebrew（推荐）
- Python 3.10 – 3.12（推荐 `brew install python@3.12`）
- Tkinter（GUI 模式必需）：`brew install python-tk@3.12`

> 提示：如果你想用其它 Python 版本，`export PYTHON=python3.11` 再运行 `setup-mac.sh` 即可。

## 快速开始

```bash
cd /path/to/glm-coding-helper
chmod +x setup-mac.sh start-backend-pipeline-gui.sh start-backend-headless.sh
./setup-mac.sh                                # 创建 .venv_paddle 并安装依赖
./start-backend-pipeline-gui.sh               # 启动 Tk 窗口 + FastAPI 后端
```

启动后：

1. Tk 窗口标题为 `GLM Coding Captcha - Pipeline Backend`，约 10 秒后状态变成绿色「● 运行中」。
2. 浏览器安装 Tampermonkey（Chrome/Edge）或 Userscripts（Safari），从 Greasy Fork 或本仓库安装 `glm-coding-helper.user.js`。
3. 打开 <https://www.bigmodel.cn/glm-coding>，触发验证码弹窗，控制台会打印 `[glm-captcha-direct] sending...`，Tk 窗口的「最近识别结果」会出现新条目。

只想要 FastAPI 不要 Tk 窗口（适合远程 / 后台）：

```bash
./start-backend-headless.sh
```

## 工作原理

- `setup-mac.sh` 调用 `python3 scripts/setup_backend.py --target cpu`，创建 `.venv_paddle` 并安装 `requirements-backend-mac.txt`（精简版，移除了 Windows-only 的 `pydirectinput`）。
- `start-backend-pipeline-gui.sh` 自动设置 `CNCAPTCHA_OCR_MODE=cpu` 和 `CNCAPTCHA_YOLO_DEVICE=cpu` 后启动 `backend/gui.py`，由 GUI 内嵌启动 `python -m backend.server`（FastAPI，端口 8888）。
- 后端使用 YOLO 检测 + PP-OCRv5 OCR，与 Windows 版共用同一份 Python 代码（已在 `scripts/tools/captcha_worker.py`、`scripts/tools/backend_config.py` 等处加入 `os.name` / `sys.platform` 守卫）。

## 已知限制

1. **CPU only** —— PaddlePaddle 官方没有 Apple MPS / Metal 实现，YOLO 也走 CPU。
   - YOLO 推理：~150ms/张
   - PP-OCRv5 识别：~600ms/裁剪
   - 端到端：~2–3 秒/次
   - 适合单窗口（推荐 1–2 个浏览器窗口）。可在启动后修改 `config.json` 里的 `workers` / `ocr_workers` 调小。

2. **截屏流程不可用** —— `scripts/monitor/window_helper.py` 用的是 Win32 API（`EnumWindows` / `ImageGrab`），在 macOS 上不存在。传统的 `/captcha` + 浏览器自动截屏流程不能使用。
   - **必须使用油猴脚本的 base64 流程** `/captcha_direct`。油猴脚本默认就是这条路径，所以正常安装使用即可。

3. **`pydirectinput` 不可用** —— 已从 `requirements-backend-mac.txt` 中移除。油猴脚本点击走的是 `element.click()` DOM 事件，不依赖 `pydirectinput`。

4. **Tk 字体回退** —— `Microsoft YaHei UI` / `Consolas` 在 macOS 上不存在，Tk 会回退到系统默认字体（PingFang SC / Menlo）。仅影响观感，不影响功能。

5. **进程亲和性 no-op** —— `p.cpu_affinity()` 在 macOS 上 `try/except` 静默失败，worker 由 macOS 调度器自动分配核心。比 Windows 上显式绑核略慢，但能用。

6. **多窗口建议** —— M1 8 核机器推荐 1–2 个浏览器窗口。可在 `config.json` 调整 worker 数：
   ```json
   {
       "workers": 1,
       "ocr_workers": 2,
       "port": 8888
   }
   ```

## 故障排除

### `ModuleNotFoundError: No module named 'tkinter'`

Tkinter 没装或装到了别的 Python 上。

```bash
brew install python-tk@3.12
# 确认安装到了当前 python3
python3 -c "import tkinter; print(tkinter.TkVersion)"
```

### `paddlepaddle` 安装失败 / 编译错误

Paddle 3.3.1 官方有 macOS ARM64 + x86_64 wheels。确保用的是 Python 3.10–3.12，并且 `pip` 较新：

```bash
python3 -m pip install --upgrade pip
./setup-mac.sh --recreate
```

如果仍然失败，可尝试锁定到 Paddlex 3.3.10（已知与 Paddle 3.3.1 在某些 Mac 环境更稳）：

```bash
./.venv_paddle/bin/pip install 'paddlex==3.3.10'
```

### Tk 窗口不出现

从终端启动看错误：

```bash
./start-backend-pipeline-gui.sh
```

常见问题：Tcl/Tk 没装（`brew install python-tk@3.12`），或 LaunchServices 索引损坏（`/System/Library/Frameworks/Tk.framework` 异常）。

### 端口 8888 被占用

`./start-backend-pipeline-gui.sh` 会用 `lsof` 自动检测并询问是否 kill。如果要手动查：

```bash
lsof -nP -iTCP:8888 -sTCP:LISTEN
kill -9 <PID>
```

### 验证码识别慢

- 把 `config.json` 里的 `ocr_workers` 调小（默认会按 CPU 核心数自动算）。
- 用 `CNCAPTCHA_CPU_OCR_MODEL=mobile_rec ./start-backend-pipeline-gui.sh` 强制使用更小的 `PP-OCRv5_mobile_rec` 模型（准确率略降但快 ~2x）。

## 关键文件改动摘要

> 维护者请看 [`mac_port_notes.md`](mac_port_notes.md)，里面有完整的行号、改动原因、未修改的 Windows 行为、回归风险分析。

## 关键文件改动摘要

| 文件 | 改动 |
|------|------|
| `scripts/tools/captcha_worker.py` | `OCR_PYTHON` 默认值用 `os.name` 区分 `Scripts/python.exe` vs `bin/python` |
| `scripts/tools/backend_config.py` | `_gpu_probe_env` 中 `USERPROFILE` 守卫到 Windows |
| `scripts/tools/ppocr_cpu_pool_worker.py` | 同上 |
| `scripts/setup_backend.py` | Mac 自动用 `requirements-backend-mac.txt`；GPU smoke test 守卫到 Windows |
| `scripts/monitor/window_helper.py` | 非 Windows 平台抛 `ImportError`，被 `captcha_server.py` 静默吞掉 |
| `scripts/tools/captcha_server.py` | `capture_browser_window is None` 时显式早返回，给出明确错误 |
| `requirements-backend-mac.txt` | **新增**，移除了 `pydirectinput` / `mss` |
| `setup-mac.sh` | **新增** |
| `start-backend-pipeline-gui.sh` | **新增** |
| `start-backend-headless.sh` | **新增** |

## 卸载

```bash
rm -rf .venv_paddle .paddle_home .paddlex_cache_cpu
```
