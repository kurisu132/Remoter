# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

基于 PySide6 的实时 RTSP 摄像头监控 GUI 应用，具备 OpenGL 硬件加速渲染、PTZ（云台）控制和补光灯控制功能。目标设备为 5MP IP 摄像头，地址 `rtsp://192.168.1.36:554/ch01.264`（分辨率 2592×1904）。

## 安装依赖

包管理使用 **uv**（见 `pyproject.toml`）。

```bash
# 首次安装 uv（OrangePi Ubuntu 22.04）
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env          # 或重新打开终端

# 安装所有依赖（自动创建 .venv）
uv sync

# ARM64 / OrangePi 跳过 C 扩展（PyOpenGL-accelerate 无 ARM64 轮子）：
# uv sync  即可，opengl-accel 是可选项，默认不安装

# x86 开发机如需加速扩展：
# uv sync --extra opengl-accel

# Ubuntu 串口权限（首次，重新登录生效）
sudo usermod -aG dialout $USER
```

FFmpeg 需要系统级安装：
```bash
sudo apt install ffmpeg
```

## 运行应用

```bash
# 方式 A：通过 uv run（自动使用 .venv）
uv run python gui/main_window.py

# 方式 B：激活虚拟环境后直接运行
source .venv/bin/activate
python gui/main_window.py

# 独立测试脚本
python check.py                        # OpenGL + FFmpeg 集成冒烟测试（实机首跑必做）
python stream/ffmpeg_player.py         # 纯流媒体测试（QLabel 显示）
python stream/stm32_reader.py          # STM32 串口读取测试
python stream/udp_control_sender.py    # UDP 发送测试（目标 127.0.0.1:9000）
python gui/opengl_checker.py           # OpenGL 库可用性检测
python api/light_control.py            # 补光灯控制测试
```

## 架构说明

数据流向：**FFmpeg 子进程 → `FFmpegRTSPPlayer`（QThread）→ `VideoOpenGLWidget`（OpenGL）→ 屏幕**

### 各层职责

**`stream/ffmpeg_player.py`** — `FFmpegRTSPPlayer(QThread)`
- 启动 FFmpeg 子进程，使用低延迟参数和 4 线程 slice 级并行 H.264 解码
- 从 stdout 管道读取原始 RGB24 帧，通过 `frame_updated(QImage)` 信号发送到 UI 线程
- 发生错误时发射 `error_occurred(str)` 信号

**`gui/video_opengl_widget.py`** — `VideoOpenGLWidget(QOpenGLWidget)`
- 通过 `update_frame()` 接收 `QImage` 帧并上传到 GPU 纹理
- 使用 OpenGL 3.3 Core Profile GLSL 着色器渲染（VAO + VBO 管线）
- VBO 纹理坐标做了 Y 轴翻转，以修正 QImage 方向
- 销毁前需调用 `cleanup()` 释放 GPU 资源

**`gui/main_window.py`** — `MainWindow(QWidget)`
- 直接运行时的程序入口；从 `ui/window_ui.py` 加载 `Ui_Camera`
- 将 `FFmpegRTSPPlayer.frame_updated` 连接到 `VideoOpenGLWidget.update_frame`
- 支持 F11/ESC 切换全屏，`closeEvent` 中完整释放所有资源

**`api/ptz_control.py`** — `PTZControlClient`
- 通过 HTTP POST 到 `/digest/frmPTZControl` 控制云台
- 使用持久 `requests.Session` 进行手动 HTTP Digest 认证（两步流程：401 → 带认证头重发）
- PTZ 命令码：20=停止，21=上，22=下，23=左，24=右

**`api/light_control.py`** — `LightControlClient`
- 通过 `/digest/frmIotLightCfg` 控制补光灯
- 相同的 Digest 认证模式，但每次请求使用新会话（无状态）

**`api/digest_auth.py`** — `digest_auth_request(config)`
- 通用 Digest 认证辅助函数，支持 3 次重试，用于一次性请求

### OpenGL 关键约束

`QSurfaceFormat`（OpenGL 3.3 Core Profile）**必须在创建 `QApplication` 之前设置**，否则 OpenGL 上下文将无法正确初始化。参见 `gui/main_window.py` 中 `if __name__ == "__main__"` 块里的初始化顺序。

### UI 提升控件

`ui/window_ui.py` 将 `video_widget` 实例化为提升类型 `VideoOpenGLWidget`。布局中的标准 `QOpenGLWidget`（`openGLWidget`）当前未用于渲染，所有视频均通过 `video_widget` 显示。
