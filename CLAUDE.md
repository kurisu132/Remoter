# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

基于 PySide6 的实时 RTSP 摄像头监控 GUI 应用，具备 OpenGL 硬件加速渲染、STM32 摇杆输入、UDP 控制输出、PTZ（云台）控制和补光灯控制功能。

- **目标硬件**：OrangePi 5（RK3588S，ARM64，Ubuntu 22.04，Mali-G610）
- **目标摄像头**：5MP IP 摄像头，`rtsp://192.168.1.36:554/ch01.264`（分辨率 2592×1904）
- **工控机 UDP**：目标地址 `192.168.1.11:9000`，协议见 REMOTE_PROTOCOL_v1

详细架构见 `ARCHITECTURE.md`。

## 文档体系

| 文件 | 用途 |
|---|---|
| `CLAUDE.md` | 开发指南（本文件） |
| `ARCHITECTURE.md` | 架构详情、模块边界、数据流 |
| `LESSONS.md` | 判断与复盘日志——发现预期与实际的落差时记录，格式见文件头模板 |

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

## 配置文件

项目根目录的 `config.toml`（已提交进 git，直接编辑即可）：

```toml
# 工控机 UDP 目标地址；UI 中「连接」按钮会写回 target_ip
target_ip   = "192.168.1.11"
target_port = 9000

# 摄像头连接信息（出厂默认密码，非敏感）
camera_host = "192.168.1.36"
camera_user = "admin"
camera_pass = "123456"

# 串口路径：Linux /dev/ttyACM0，Windows COM3
stm32_port  = "/dev/ttyACM0"
```

- `stm32_port`：串口路径；Windows 改为 `"COM3"`（或实际端口号），无需改代码
- `target_ip`：工控机 UDP 目标 IP；UI 中"连接"按钮也会写回此字段

---

## 运行应用

```bash
# 方式 A：通过 uv run（推荐，自动使用 .venv）
uv run python -m gui.main_window

# 离线模式（无需摄像头，FFmpeg 内置测试图案）
uv run python -m gui.main_window --test

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
| `gui/main_window.py` | `MainWindow` | 应用入口，RTSP/STM32/UDP/PTZ/补光灯 生命周期管理 |
| `ui/window_ui.py` | `WindowUI` | 纯 UI 布局——widget 创建、样式表、信号连接 |
| `gui/video_opengl_widget.py` | `VideoOpenGLWidget` | OpenGL 渲染，双模 GLSL 着色器 |
| `stream/ffmpeg_player.py` | `FFmpegRTSPPlayer` | FFmpeg 子进程，NV12 帧读取，Signal(bytes,int,int) |
| `stream/stm32_reader.py` | `STM32Reader` / `ControlFrame` | STM32 串口帧解析 |
| `stream/udp_control_sender.py` | `UDPControlSender` | REMOTE_PROTOCOL_v1 UDP 发送 |
| `api/ptz_control.py` | `PTZControlClient` | PTZ 云台 HTTP 控制 |
| `api/light_control.py` | `LightControlClient` | 补光灯 HTTP 控制 |
| `api/digest_auth.py` | — | HTTP Digest 认证辅助 |

**关键约束**：`QSurfaceFormat` 必须在 `QApplication` 之前设置。

---

## 开发工作流

### 提交规范

遵循 Conventional Commits 格式：

```
<type>: <简短描述>

<详细说明（可选）>
```

**类型标识必须与改动内容一一对应，禁止一个标识内混杂多类改动：**

| 标识 | 仅限包含 | 禁止混入 |
|---|---|---|
| `feat` | 新功能、新模块、新接口 | 重构、修 bug、改文档 |
| `fix` | bug 修复、回归修正 | 新功能、重构、文档 |
| `refactor` | 结构调整、重命名、拆分/合并文件（不改变外部行为） | bug 修复、新功能、文档 |
| `style` | 格式化、缩进、样式表调整（不影响逻辑） | 布局/组件增删（属于 refactor）、bug 修复 |
| `docs` | README、CLAUDE.md、注释、ARCHITECTURE.md | 代码变动、配置调整 |
| `chore` | 构建脚本、依赖版本、`.gitignore`、CI 配置 | 源码变动 |
| `test` | 测试代码、测试配置 | 被测代码的功能改动 |

**示例：**

```bash
# ✅ 正确：修复只有一个改动类型
git commit -m "fix: 关窗后残留帧信号触发 GL_INVALID_OPERATION 1282"

# ❌ 错误：fix 里混杂了新模块和文档
git commit -m "fix: 修复 RTSP 断连并添加自动重连模块和更新文档"
#                                          ^^^^^^^^^^^^^^   ^^^^^^^^
#                                          feat → 应单独提交   docs → 应单独提交
```

**正确的做法是把不同类的改动拆成多个原子提交：**

```bash
git commit -m "fix: RTSP 断连后连接状态未重置"
git commit -m "feat: FFmpegRTSPPlayer 断连自动重连"
git commit -m "docs: CLAUDE.md 补充重连行为说明"
```

### Git Remote 配置

本项目配置两个远端：

```
origin   → GitHub（https://github.com/kurisu132/Remoter.git）存档备份
orangepi → OrangePi 直推（orangepi@192.168.5.249:/home/orangepi/PythonProjects/vlink）实机测试
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
    HostName 192.168.5.249
    User orangepi
    Port 22
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 60
    ServerAliveCountMax 3
```

OrangePi IP：192.168.5.249（路由器局域网，摄像头/Win/OrangePi 同网段）  
开发机 IP：192.168.5.34  
摄像头 IP：192.168.5.36

连接方式：VS Code → Ctrl+Shift+P → "Remote-SSH: Connect to Host..." → 选择 `orangepi`

### OrangePi 首次初始化

```bash
# OrangePi 上（仅首次）
mkdir -p ~/PythonProjects/vlink
cd ~/PythonProjects/vlink
git init
git config receive.denyCurrentBranch updateInstead

# Windows 上添加 remote（仅首次）
git remote add orangepi orangepi@192.168.5.249:/home/orangepi/PythonProjects/vlink
```

---

## 视频管道关键约束（修改前必读）

以下参数经过多次实战验证，**未经测试不得修改**：

| 参数 / 位置 | 值 | 禁止改动的原因 |
|---|---|---|
| `stream/ffmpeg_player.py` — `bufsize` | `frame_size`（`width×height×3//2`，NV12） | 背压机制，防止帧在 pipe 中堆积；改为 `-1` 会导致延迟从 ~500ms 线性增长到数秒 |
| `_build_cmd()` — `-rtsp_transport` | `tcp` | UDP 丢包会造成 NV12 字节流错位，花屏无法恢复，只能用 TCP |
| `_build_cmd()` — `-max_delay` | `0` | 消除 FFmpeg RTSP 解复用器默认 5 秒内部缓冲 |
| `_build_cmd()` — `-c:v h264_rkmpp` | Linux 上启用 | 香橙派 5MP 软解仅 10fps，低于摄像头帧率，只有硬解才能消除积压 |
| `_build_cmd()` — `-pix_fmt nv12` | 必须保持 NV12 | 切回 rgb24 会触发 swscaler，ARM 无 SIMD 加速，I 帧耗时 100-200ms（2026-07 已验证） |
| `stderr=sp.PIPE` + `_drain_stderr()` 线程 | 必须同时存在 | 无 drain 线程则 64KB stderr 管道写满后 FFmpeg/Python 双向死锁（2026-07 已验证） |

新增 FFmpeg 参数前，先查 `LESSONS.md` 确认该方向是否已尝试过。

---

## 注意事项

- OrangePi 直连网线后**无法访问 GitHub**（无互联网路由），使用直推方式开发
- 摄像头 `192.168.1.36` 需要单独网络链路，直连时不可达——开发时使用 `--test` 模式
- `libGL error: failed to load driver: rockchip` 是 OrangePi 上的无害警告，Mesa Panfrost 接管后 OpenGL 3.3 Desktop 正常工作
