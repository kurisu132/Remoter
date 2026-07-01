# ARCHITECTURE.md

> **最后同步**：Phase 1 重构完成后（dev/phase1-refactor）。如有结构变更请同步更新本文件。

## 1. 系统概览

基于 PySide6 的实时 RTSP 摄像头监控桌面应用，目标部署设备为 OrangePi 5（RK3588S，ARM64，Ubuntu 22.04，Mali-G610 GPU）。

系统由五层组成：

| 层 | 目录/文件 | 职责简述 |
|---|---|---|
| 流媒体层 | `stream/ffmpeg_player.py` | FFmpeg 子进程驱动帧采集 |
| 渲染层 | `gui/video_opengl_widget.py` | OpenGL 纹理上传与 GLSL 渲染 |
| UI 布局层 | `ui/window_ui.py` | 纯 UI 布局——widget 创建、样式表、信号连接 |
| 业务逻辑层 | `gui/main_window.py` | 生命周期管理、资源调度、事件处理 |
| 控制层（输入） | `stream/stm32_reader.py` | STM32 串口帧读取与解析 |
| 控制层（输出） | `stream/udp_control_sender.py` | UDP 控制帧封装与发送（50 Hz） |
| 摄像头 API 层 | `api/` | PTZ 云台、补光灯 HTTP 控制 |

数据依赖方向：UI 层依赖流媒体层和渲染层；控制层与渲染/流媒体层完全解耦，仅与 UI 层通过 Qt 信号交互。

---

## 2. 分层与职责

| 层 | 文件 | 职责 | 不该做什么 |
|---|---|---|---|
| UI 布局层 | `ui/window_ui.py` | 纯 UI 布局（`WindowUI.setup_ui(self)`）；widget 创建、样式表、信号连接；无业务逻辑 | 启动线程；处理业务事件 |
| 业务逻辑层 | `gui/main_window.py` | 调用 `WindowUI.setup_ui(self)` 构建 UI；管理 RTSP/STM32/UDP/PTZ/补光灯生命周期；F11/ESC 全屏；closeEvent 有序释放资源 | 直接创建 widget；解析协议帧 |
| 渲染层 | `gui/video_opengl_widget.py` | OpenGL 纹理创建与帧上传；GLSL 双模着色器（Desktop / ES）；VAO/VBO 管理；GPU 资源清理 | 知道 RTSP URL；做任何网络操作 |
| 流媒体层 | `stream/ffmpeg_player.py` | FFmpeg 子进程启动/终止；从 stdout 读 RGB24 裸帧；封装为 QImage（deep copy）通过信号发送 | 直接操作 UI；知道 OpenGL 细节 |
| STM32 输入 | `stream/stm32_reader.py` | 串口帧同步与解析；发射 `frame_received(ControlFrame)` 信号 | 知道 UDP 目标；做任何网络操作 |
| UDP 输出 | `stream/udp_control_sender.py` | 50 Hz 定时发送 REMOTE_PROTOCOL_v1 帧；线程安全更新控制值；运行时切换目标 IP | 知道串口细节；直接读 STM32 |
| PTZ 控制 | `api/ptz_control.py` | HTTP Digest 认证 PTZ 控制（持久 Session）| 知道视频流 |
| 补光灯控制 | `api/light_control.py` | HTTP Digest 认证灯控（无状态，每次新 Session）| 知道视频流 |
| Digest 辅助 | `api/digest_auth.py` | 通用一次性 Digest 认证（3 次重试，10s 超时）| |
| 工具 | `gui/opengl_checker.py` | 运行时检测 OpenGL 可用性（仅 import 检查，无副作用）| 修改全局 QSurfaceFormat |
| 冒烟测试 | `check.py` | 端到端集成测试；支持 `--test` 离线测试源 | 引用 main_window 内部实现 |

---

## 3. 关键数据流

### 3.1 视频帧渲染路径（最高频）

```
摄像头传感器
  → H264 编码器（相机 CPU）                [编码延迟 50-200ms，受 I 帧间隔影响]
  → RTSP/TCP 网络传输                     [LAN 直连 <1ms]
  → FFmpeg RTSP demux（max_delay=0）      [≈0ms]
  → H264 解码                             [软解 5MP: ~100ms/帧；软解 720P: ~10ms/帧；
                                           RK3588 硬解 h264_rkmpp: <10ms/帧]
  → rawvideo stdout pipe
  → FFmpegRTSPPlayer.run() stdout.read()  [阻塞，等 FFmpeg 完成一帧]
      numpy 零拷贝 → QImage deep copy
  → Signal: frame_updated(QImage)         [跨线程 QueuedConnection，<1ms]
  → VideoOpenGLWidget.update_frame()
      makeCurrent + numpy + glTexImage2D  [5MP: 20-46ms；720P: 3-8ms]
  → repaint() → paintGL()                [vsync ~16ms]
  → 屏幕
```

**各平台实测延迟（稳态，2026-06-29）**

| 配置 | 解码帧率 | 稳定延迟 | 备注 |
|---|---|---|---|
| Windows x86，5MP，软解 | 40-60fps | <200ms | CPU 算力充足，不积压 |
| OrangePi，5MP，软解 | 10-11fps | 随时间无限增长 | decode < send → TCP 积压 |
| OrangePi，720P，软解 | ~30fps | ~500ms | 积压消失，稳定 |
| OrangePi，5MP，h264_rkmpp（计划中） | ~15fps | 预期 200-400ms | VPU 硬解，消除 CPU 瓶颈 |

**5MP 软解延迟无限增长根因**：OrangePi 软解上限 ~10fps，摄像头发 15fps，每秒净积压 5 帧。
运行 20s → 积压 100 帧 ÷ 15fps = **6.7s 延迟**。调 FFmpeg 参数无法解决，根治需硬件解码。

### 3.2 STM32 控制路径（~50 Hz）

```
STM32 USB CDC (/dev/ttyACM0) 或 UART (/dev/ttyS2)
  → STM32Reader._read_loop() [QThread]
      帧同步 (0xAB) + 校验和验证
  → Signal: frame_received(ControlFrame)
  → MainWindow._on_stm32_frame()
      更新状态指示灯
      UDPControlSender.update(frame)  [线程安全]
  → UDPControlSender.run() [QThread, 50 Hz 定时器]
      build_udp_frame() → sendto()
  → 工控机 UDP 9000 端口
```

### 3.3 应用启动顺序（有硬性约束）

```
1. QSurfaceFormat 设置（3.3 Core Profile / 4x MSAA）
2. QApplication 创建
3. MainWindow.__init__()
   ├── WindowUI.setup_ui(self)  → VideoOpenGLWidget, 状态指示灯, IP 输入框, 右侧控制面板
   ├── _start_rtsp()            → FFmpegRTSPPlayer.start()
   ├── _start_stm32()           → STM32Reader.start()（串口路径从 config 读）
   ├── _start_udp_sender()      → UDPControlSender.start()
   └── _start_camera_clients()  → PTZControlClient + LightControlClient（凭证从 config 读）
```

### 3.4 运行时 IP 切换

```
UI"连接"按钮 → MainWindow._on_connect()
    读取 IP 输入框文本
    UDPControlSender.set_target(ip, port)  [threading.Lock 保护]
        内部调用 save_config()            → 写回 ~/.vlink/config.toml
```

### 3.5 关闭路径（资源释放顺序）

```
closeEvent
  ├── 断开 RTSP 信号
  ├── rtsp_player.stop() → wait(2000) → [超时] terminate() + wait(500)
  ├── stm32.stop()       → wait(1000)
  ├── udp_sender.stop()  → wait(1000)
  └── video_widget.cleanup()  [在 GL 上下文内释放 VAO/VBO/纹理/着色器]
```

---

## 4. 关键数据结构

### ControlFrame（`stream/stm32_reader.py`）

STM32 帧格式（可扩展变长帧，v1 = 9 字节）：

```
Byte 0  : 0xAB  同步头
Byte 1  : version  当前 0x01
Byte 2  : length   payload 字节数（v1 = 5）
Byte 3-4: left   int16 LE，[-255, +255]
Byte 5-6: right  int16 LE，[-255, +255]
Byte 7  : flags  bit0=ESTOP  bit1=REMOTE_ACTIVE
[v2+]   : digital_N ...（旧解析器自动忽略）
Byte N  : checksum  sum(bytes[0..N-1]) & 0xFF
```

### UDP 帧（REMOTE_PROTOCOL_v1，8 字节）

```
Byte 0  : 0x12  header
Byte 1  : 0x10  CMD = MOTION
Byte 2-3: left  int16 LE
Byte 4-5: right int16 LE
Byte 6  : flags（同 ControlFrame.flags）
Byte 7  : checksum  sum(bytes[0..6]) & 0xFF
```

---

## 5. 全局约定与陷阱

### OpenGL 初始化顺序（硬性约束）
`QSurfaceFormat` **必须在 `QApplication` 构造之前**设置。`gui/main_window.py` 和 `check.py` 的 `__main__` 块均遵守此约定。

### OpenGL 双模 GLSL
`VideoOpenGLWidget` 在 `initializeGL` 中调用 `self.context().isOpenGLES()` 运行时检测，根据结果选择：
- **Desktop**：`#version 330 core`（x86 / OrangePi Mesa Panfrost）
- **ES**：`#version 300 es` + `precision mediump float;`（纯 OpenGL ES 环境）

OrangePi 5 实测：Mesa Panfrost 运行 **OpenGL 3.3 Desktop**，libGL 的 rockchip/dri3 报错为无害警告。

### QImage 必须 deep copy
`FFmpegRTSPPlayer` 将 numpy buffer 包装为 `QImage` 后须立即 `.copy()`，否则 buffer 随栈帧释放后 `QImage` 指向悬空内存。

### `VideoOpenGLWidget.cleanup()` 需在 GL 上下文内调用
方法内部调用 `makeCurrent()` 保证上下文激活；调用方需在 widget 仍有效时执行（`closeEvent` 中），不能推迟到 `QApplication` 析构阶段。

### `stop()` 不调用 `wait()`
`FFmpegRTSPPlayer.stop()`、`STM32Reader.stop()`、`UDPControlSender.stop()` 均只发信号，**不** 调用 `self.wait()`。调用方（`closeEvent`）负责等待和超时处理。

### 串口权限（Ubuntu 首次）
```bash
sudo usermod -aG dialout $USER   # 重新登录生效
```

### PTZ 与补光灯 Session 策略不一致
`PTZControlClient` 使用持久 `requests.Session`（Keep-Alive），`LightControlClient` 每次请求创建新 Session（无状态）。

### 状态指示灯（右侧面板三个圆点）
- **RTSP**：`_on_rtsp_status(status)` 驱动；`"streaming"` → 绿，其余 → 黄
- **STM32**：`_on_stm32_frame` 时置绿，`_on_stm32_error` 时置红
- **UDP**：`_on_udp_error` 时置红，同时启动 2 秒单次定时器 `_refresh_udp_indicator()` 自动恢复

---

## 6. 平台差异与性能边界

### x86（Windows 开发机）vs ARM（OrangePi 5）软解对比

| 指标 | Windows x86 | OrangePi ARM64 |
|---|---|---|
| H264 软解 5MP 帧率 | 40-60fps | **~10fps（上限）** |
| GL texUpload 5MP | ~0ms（驱动 DMA） | 17-46ms（CPU→GPU 拷贝） |
| GL texUpload 720P | ~0ms | 3-8ms |
| 首帧延迟 | ~900ms | ~3500ms |

OrangePi GL 上传慢的原因：Mesa Panfrost 驱动不做 DMA 零拷贝，`glTexImage2D` 需要
CPU 将 numpy 数组（14.8MB）拷贝到 GPU 可访问内存，耗时随帧大小线性增长。

### 当前 FFmpeg 命令关键参数（`stream/ffmpeg_player.py` `_build_cmd()`）

```
-rtsp_transport tcp      # UDP 丢包会造成 RGB24 字节错位花屏，必须 TCP
-fflags nobuffer         # 禁用 FFmpeg 内部 I/O 缓冲
-flags low_delay         # 降低解码器内部延迟
-max_delay 0             # RTSP demuxer 最大缓冲设为 0（默认 5s）
-probesize 2048          # 最小探测字节数（32 太激进会连接失败）
-analyzeduration 100000  # 0.1s 流分析（原 1s），减少首帧延迟
```

Linux（OrangePi）额外加 `-c:v h264_rkmpp`（已在计划中实施）。

### RK3588 硬件解码路线图

**状态**：`h264_rkmpp` 已确认内置于 `/usr/bin/ffmpeg`，待实施。

**实施方式**（仅改 `_build_cmd()`）：
```python
import sys
hw_decoder = ["-c:v", "h264_rkmpp"] if sys.platform != "win32" else []
# 插入 -i 之前；FFmpeg 遇到软件 scale 滤镜自动插入 hwdownload+NV12 转换
```

**预期效果**：
- 5MP H264 解码 <10ms/帧（vs 软解 ~100ms）
- 摄像头可恢复 5MP/15fps，TCP 积压消失
- 稳定延迟预期 200-400ms（接近 720P 软解的 500ms，但分辨率恢复）

**后续优化**（NV12 管道）：让 FFmpeg 输出 NV12（1.5B/px）而非 RGB24（3B/px），
GL 上传量减半（7.4MB vs 14.8MB），需修改 `video_opengl_widget.py` 着色器
加入 YUV→RGB 转换逻辑。

---

## 7. 配置系统

配置文件：项目根目录 `config.toml`（已提交进 git）

| 读取方 | 字段 |
|---|---|
| `_start_stm32()` | `stm32_port` |
| `_start_camera_clients()` | `camera_host` / `camera_user` / `camera_pass` |
| `UDPControlSender.__init__()` | `target_ip` / `target_port` |

写入：UI"连接"按钮触发 `UDPControlSender.set_target()` → 内部 `save_config()`，仅更新 `target_ip`。
