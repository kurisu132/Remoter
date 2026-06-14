# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

基于 PySide6 的实时 RTSP 摄像头监控 GUI 应用，具备 OpenGL 硬件加速渲染、STM32 摇杆输入、UDP 控制输出、PTZ（云台）控制和补光灯控制功能。

- **目标硬件**：OrangePi 5（RK3588S，ARM64，Ubuntu 22.04，Mali-G610）
- **目标摄像头**：5MP IP 摄像头，`rtsp://192.168.1.36:554/ch01.264`（分辨率 2592×1904）
- **工控机 UDP**：目标地址 `192.168.1.11:9000`，协议见 REMOTE_PROTOCOL_v1

详细架构见 `ARCHITECTURE.md`。

---

## 安装依赖

包管理使用 **uv**（见 `pyproject.toml`）。

```bash
# 首次安装 uv（OrangePi Ubuntu 22.04）
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env          # 或重新打开终端

# 安装所有依赖（自动创建 .venv）
uv sync

# ARM64 / OrangePi：跳过 C 扩展（PyOpenGL-accelerate 无 ARM64 轮子），uv sync 即可
# x86 开发机如需加速扩展：
# uv sync --extra opengl-accel

# Ubuntu 串口权限（首次，重新登录生效）
sudo usermod -aG dialout $USER
```

FFmpeg 需要系统级安装：
```bash
sudo apt install ffmpeg
```

---

## 运行应用

```bash
# 方式 A：通过 uv run（推荐，自动使用 .venv）
uv run python gui/main_window.py

# 方式 B：激活虚拟环境后直接运行
source .venv/bin/activate
python gui/main_window.py
```

### 测试脚本

```bash
# 集成冒烟测试（实机首跑必做）
uv run python check.py              # 需要连接摄像头
uv run python check.py --test       # 离线模式（FFmpeg 内置测试图案，无需摄像头）

# 各层独立测试
uv run python stream/ffmpeg_player.py     # 纯流媒体测试（QLabel 显示）
uv run python stream/stm32_reader.py      # STM32 串口读取测试（需连接硬件）
uv run python stream/udp_control_sender.py  # UDP 发送测试（目标 127.0.0.1:9000）
uv run python gui/opengl_checker.py       # OpenGL 库可用性检测
uv run python api/light_control.py        # 补光灯控制测试
```

---

## 架构说明

详见 `ARCHITECTURE.md`。以下是快速索引：

| 文件 | 类 | 职责 |
|---|---|---|
| `gui/main_window.py` | `MainWindow` | 应用入口，代码布局，生命周期管理 |
| `gui/video_opengl_widget.py` | `VideoOpenGLWidget` | OpenGL 渲染，双模 GLSL 着色器 |
| `stream/ffmpeg_player.py` | `FFmpegRTSPPlayer` | FFmpeg 子进程，帧读取，QImage 信号 |
| `stream/stm32_reader.py` | `STM32Reader` / `ControlFrame` | STM32 串口帧解析 |
| `stream/udp_control_sender.py` | `UDPControlSender` | REMOTE_PROTOCOL_v1 UDP 发送 |
| `api/ptz_control.py` | `PTZControlClient` | PTZ 云台 HTTP 控制 |
| `api/light_control.py` | `LightControlClient` | 补光灯 HTTP 控制 |
| `api/digest_auth.py` | — | HTTP Digest 认证辅助 |

**关键约束**：`QSurfaceFormat` 必须在 `QApplication` 之前设置。

---

## 开发工作流

### Git Remote 配置

本项目配置两个远端：

```
origin   → GitHub（https://github.com/kurisu132/Remoter.git）存档备份
orangepi → OrangePi 直推（orangepi@192.168.1.10:/home/orangepi/PythonProjects/vlink）实机测试
```

查看当前配置：
```bash
git remote -v
```

### 日常开发循环

```bash
# 1. 在 Windows 上编写代码（Claude Code）

# 2. 提交
git add <files>
git commit -m "..."

# 3. 推送到 OrangePi（用于测试）
git push orangepi dev/phase1-refactor

# 4. OrangePi 上拉取并测试
#    （通过 VS Code Remote SSH 或直接 SSH）
git pull   # OrangePi 端已配置 updateInstead，push 即生效，无需手动 pull
uv run python check.py --test   # 离线验证
uv run python gui/main_window.py  # 完整测试

# 5. 功能验证通过后推送到 GitHub 存档
git push origin dev/phase1-refactor
```

### VS Code Remote SSH

SSH 配置（`~/.ssh/config`）：
```
Host orangepi
    HostName 192.168.1.10
    User orangepi
    Port 22
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 60
    ServerAliveCountMax 3
```

OrangePi IP：192.168.1.10（eth0 静态 IP，直连网线）  
开发机 IP：192.168.1.12

连接方式：VS Code → Ctrl+Shift+P → "Remote-SSH: Connect to Host..." → 选择 `orangepi`

### OrangePi 首次初始化

```bash
# OrangePi 上（仅首次）
mkdir -p ~/PythonProjects/vlink
cd ~/PythonProjects/vlink
git init
git config receive.denyCurrentBranch updateInstead

# Windows 上添加 remote（仅首次）
git remote add orangepi orangepi@192.168.1.10:/home/orangepi/PythonProjects/vlink
```

---

## 注意事项

- OrangePi 直连网线后**无法访问 GitHub**（无互联网路由），使用直推方式开发
- 摄像头 `192.168.1.36` 需要单独网络链路，直连时不可达——开发时使用 `--test` 模式
- `libGL error: failed to load driver: rockchip` 是 OrangePi 上的无害警告，Mesa Panfrost 接管后 OpenGL 3.3 Desktop 正常工作
