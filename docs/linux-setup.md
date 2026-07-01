# Linux 安装与使用说明

本文档面向 **Linux 用户**，说明如何在本机安装并启动 GLM Coding Helper 的本地 OCR 后端。
Windows 用户请直接看 [README.md](../README.md)；macOS 用户请看 [macOS 安装与使用说明](macos-setup.md)。

## 适用范围

| 项 | 说明 |
| --- | --- |
| 系统 | 常见 x86_64 Linux 发行版（Arch、Ubuntu、Debian、Fedora 等） |
| 架构 | x86_64（与 PaddlePaddle / CUDA wheel 发布范围一致） |
| 后端 | **CPU** 必选；**NVIDIA GPU** 可选（需驱动 + CUDA 兼容环境）；one-click 走 `captcha_server_headless`（与 Windows 主路径同源，非 macOS 的 `backend/server.py` pipeline） |
| 验证码识别 | 与 Windows 版一致（YOLO + PaddleOCR 流水线） |

## 重要前提：Linux 版怎么识别验证码

主流程与 Windows 相同：

1. 油猴脚本从腾讯验证码组件抓取原图；
2. 原图 base64 发送到本地后端 `/captcha_direct`；
3. 后端用本地 YOLO + PaddleOCR 识别；
4. 脚本按识别坐标点击文字。

**识别不依赖屏幕截图**。Windows 上的自动截图验证码弹窗（`scripts/monitor/window_helper.py`）是 Win32 专用，Linux 不支持，但不影响主流程。

## 前置条件

### 1. Python 3.12 或 uv

项目固定使用 **Python 3.12**。任选其一：

**方式 A：系统安装 Python 3.12**

```bash
# Arch
sudo pacman -S python312

# Ubuntu / Debian（视发行版仓库而定）
sudo apt install python3.12 python3.12-venv

python3.12 --version
```

**方式 B：用 uv 管理（推荐，脚本会自动检测）**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12
```

若 Python 不在默认 PATH，可显式指定：

```bash
export CNCAPTCHA_PYTHON=/path/to/python3.12
```

### 2. NVIDIA GPU（可选）

`one-click-start.sh` 默认 `--target auto`：**有 NVIDIA GPU 时优先装 GPU 环境**，失败则回退 CPU。

确认驱动可用：

```bash
nvidia-smi
```

无独显或驱动未装好时，脚本会自动走 CPU 路径。

### 3. 油猴脚本

在 Chrome / Edge（Linux 版）安装 Tampermonkey 并安装 `glm-coding-helper.user.js`，步骤与 Windows 相同，见 [README.md](../README.md) 的「安装油猴脚本」一节。

### 4. 网络

首次安装会从 PyPI 拉取 PaddlePaddle、Ultralytics 等大包。`one-click-start.sh` 在未传 `--pip-arg` 时会**自动探测可用 PyPI 镜像**（清华、阿里、中科大、腾讯，最后官方源）。

## 一键安装（推荐）

下载 Release 中的 `glm-coding-helper-online-installer-*.zip` 并解压，在终端执行：

```bash
cd /path/to/glm-coding-helper
chmod +x one-click-start.sh scripts/setup_backend_linux.sh
./one-click-start.sh
```

> 从 Windows 打的 zip 解压后通常没有可执行位，**必须先 `chmod +x`**，或直接用 `bash one-click-start.sh` 启动。

脚本会自动完成：

1. 检测 Linux、NVIDIA GPU、Python 3.12 / uv；
2. 探测 PyPI 镜像并安装依赖；
3. 创建 `.venv_paddle`（CPU）和/或 `.venv_paddle_gpu`（GPU）；
4. 检查 YOLO 权重；
5. 以 **headless** 模式启动 `captcha_server` 后端（`start_backend.py --headless` → `captcha_server_headless.py`，与 Windows 主路径同源，非 macOS 的 `backend/server.py` pipeline）。

启动成功后监听：

```text
http://127.0.0.1:8888
```

可选参数：

```bash
./one-click-start.sh --target auto    # 默认：有 GPU 优先 GPU，否则 CPU
./one-click-start.sh --target cpu     # 仅 CPU
./one-click-start.sh --target gpu     # 仅 GPU
./one-click-start.sh --port 8889      # 换端口
```

## 命令行手动安装

```bash
./scripts/setup_backend_linux.sh
```

常用参数：

```bash
# 仅 CPU / 仅 GPU / 同时安装两者
./scripts/setup_backend_linux.sh --target cpu
./scripts/setup_backend_linux.sh --target gpu
./scripts/setup_backend_linux.sh --target both

# 删除并重建环境
./scripts/setup_backend_linux.sh --target cpu --recreate

# 手动指定 PyPI 镜像（跳过自动探测）
./scripts/setup_backend_linux.sh --pip-arg -i --pip-arg https://pypi.tuna.tsinghua.edu.cn/simple
```

安装完成后手动启动：

```bash
# headless（与 one-click-start.sh 相同）
./.venv_paddle_gpu/bin/python scripts/tools/start_backend.py --headless --mode auto --port 8888

# 仅 CPU
./.venv_paddle/bin/python scripts/tools/start_backend.py --headless --mode cpu --port 8888
```

## 虚拟环境与模式

| 目录 | 用途 |
| --- | --- |
| `.venv_paddle` | CPU 后端 |
| `.venv_paddle_gpu` | GPU 后端（需 NVIDIA + CUDA 兼容 Paddle wheel） |

`--mode auto` 会优先用 GPU OCR，失败时回退 CPU（需两个环境都已安装）。

## 已知限制

| 限制 | 说明 |
| --- | --- |
| **无 Win32 截图弹窗** | 与 macOS 相同，走油猴脚本 `/captcha_direct` 发图 |
| **GPU 依赖环境** | 需 NVIDIA 驱动、CUDA 与 `requirements-backend-gpu.txt` 中的 Paddle GPU wheel 匹配 |
| **首次模型下载** | PaddleOCR 首次运行会联网下载模型，请耐心等待 |
| **zip 可执行位** | Release zip 在 Linux 上解压后需 `chmod +x`，见上文 |

## 端口占用排查

```bash
ss -tlnp | grep 8888
# 或
lsof -i :8888

kill <PID>
```

换端口：

```bash
CNCAPTCHA_PORT=8889 ./one-click-start.sh
```

油猴脚本默认连 `http://127.0.0.1:8888`，换端口后需在脚本配置里同步修改。

## 安装后验证

```bash
./.venv_paddle/bin/python -c "import fastapi, uvicorn, psutil, ultralytics, paddleocr, paddlex, paddle, cv2, PIL, numpy; print('依赖导入正常')"
```

有 GPU 环境时：

```bash
./.venv_paddle_gpu/bin/python -c "import paddle; print('cuda=', paddle.is_compiled_with_cuda())"
```

启动后端并检查健康接口：

```bash
./one-click-start.sh &
curl http://127.0.0.1:8888/health
```

## Linux 与 Windows / macOS 差异

| 项 | Windows | macOS | Linux |
| --- | --- | --- | --- |
| 一键启动 | `one-click-start.cmd` | `one-click-start.command` | `one-click-start.sh` |
| one-click 后端 | `captcha_server.py`（Tk） | `backend.server` pipeline（headless） | `captcha_server_headless.py` |
| 日常 GUI | one-click 自带 Tk | `start-backend-pipeline-gui.command` → `backend/gui.py` | 无（可手动 `start_backend.py` 不带 `--headless`，需 tkinter） |
| GPU | 支持 | 不支持 | 支持（NVIDIA） |
| 环境搭建 | `bootstrap_windows.ps1` | `setup_backend_macos.sh` | `setup_backend_linux.sh` |
| PyPI 镜像 | 自动探测 | 需手动 `--pip-arg` | 自动探测 |

## 常见问题

### `Permission denied` 运行 `./one-click-start.sh`

```bash
chmod +x one-click-start.sh scripts/setup_backend_linux.sh
# 或
bash one-click-start.sh
```

### 没有找到 Python 3.12

安装系统 Python 3.12，或安装 uv 后执行 `uv python install 3.12`。

### `pip install` 很慢或超时

脚本默认会自动探测国内镜像。若仍失败，手动指定：

```bash
./one-click-start.sh --pip-arg -i --pip-arg https://pypi.tuna.tsinghua.edu.cn/simple
```

### GPU 安装失败，auto 模式还能用吗？

可以。`one-click-start.sh` 在 auto 模式下 GPU 失败会自动回退 CPU，并尝试预装 CPU fallback 环境。

### 安装日志在哪？

```text
logs/backend-install.log
```

排查环境问题时请附上此文件。
