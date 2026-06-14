# ARCHITECTURE.md

## 1. 系统概览

本项目是一个基于 PySide6 的实时 RTSP 摄像头监控桌面应用，目标设备为 5MP IP 摄像头（分辨率 2592×1904）。
核心由四大块组成：**流媒体层**（FFmpeg 子进程驱动的帧采集线程）、**渲染层**（OpenGL 3.3 Core Profile 硬件加速显示）、**控制层**（PTZ 云台与补光灯 HTTP API）以及**UI 描述层**（Qt Designer 生成的布局文件）。
数据依赖方向：主窗口依赖流媒体层和渲染层；渲染层通过 Qt 信号与流媒体层解耦，自身不感知 RTSP；控制层完全独立于渲染/流媒体层，仅通过 HTTP 与摄像头通信。

---

## 2. 分层与职责

| 层 | 职责 | 不该做什么 | 依赖谁 |
|---|---|---|---|
| `gui/main_window.py` | 应用入口；窗口/全屏生命周期；将流媒体信号连接到渲染层；资源有序释放 | [确认] | `stream/ffmpeg_player.py`、`gui/video_opengl_widget.py`、`ui/window_ui.py` |
| `gui/video_opengl_widget.py` | OpenGL 纹理创建与帧上传（`glTexImage2D`）；GLSL 着色器编译；VAO/VBO 管理；GPU 资源清理 | [确认] | PyOpenGL、PySide6 QtOpenGLWidgets |
| `stream/ffmpeg_player.py` | FFmpeg 子进程启动与终止；从 stdout 管道读取 RGB24 原始帧；封装为 `QImage`（deep copy）并通过信号发送 | [确认] | FFmpeg 可执行文件（运行时 `shutil.which` 定位）、numpy |
| `api/ptz_control.py` | PTZ 云台方向控制（上/下/左/右/停止）；持久 `requests.Session` 保持长连接 | [确认] | requests |
| `api/light_control.py` | 补光灯开关与亮度设置；每次请求使用全新 session（无状态） | [确认] | requests |
| `api/digest_auth.py` | 通用一次性 HTTP Digest 认证辅助（支持 3 次重试、10s 超时） | [确认] | requests |
| `ui/window_ui.py` | Qt Designer 生成的布局与样式定义（禁止手动编辑） | [确认] | PySide6；提升控件 `VideoOpenGLWidget` |
| `gui/opengl_checker.py` | 运行时检测 OpenGL 可用性并提供用户可读的降级原因 | [确认] | PyOpenGL、PySide6（懒加载） |
| `check.py` | OpenGL + FFmpeg 集成冒烟测试（独立可执行，不依赖 `gui/main_window.py`） | [确认] | `stream/ffmpeg_player.py`、PyOpenGL、PySide6 |

---

## 3. 关键数据流

### 3.1 视频帧渲染路径（最高频路径）
FFmpeg 子进程通过 stdout 管道持续输出 RGB24 裸流 →
`FFmpegRTSPPlayer.run()`（QThread）用 numpy 零拷贝读取缓冲区，再 deep copy 封装为 `QImage` →
Qt 信号 `frame_updated(QImage)` 自动跨线程投递到 UI 线程 →
`VideoOpenGLWidget.update_frame()` 调用 `glTexImage2D()` 上传 GPU 纹理 →
`paintGL()` 中 GLSL 着色器采样纹理并输出到屏幕。

### 3.2 摄像头 API 控制路径（PTZ 为例）
GUI 事件触发 `PTZControlClient` 便捷方法（如 `pan_left()`）→
内部调用 `_send_ptz_request(payload)`：先发一次无认证 POST，收到 401 响应 →
从 `WWW-Authenticate` 头用 regex 提取 nonce/realm/opaque →
手动计算 MD5 Digest 并构造 `Authorization` 头 →
带认证头重发 POST，解析 JSON 响应；全程严格检测 500ms 超时预算。

### 3.3 应用启动路径（初始化顺序有硬性约束）
`if __name__ == "__main__"` 块中先设置 `QSurfaceFormat`（OpenGL 3.3 Core Profile，4x MSAA）→
再创建 `QApplication` →
`MainWindow.__init__()` 调用 `Ui_Camera.setupUi()` 实例化布局（含提升后的 `VideoOpenGLWidget`）→
`_start_rtsp_playback()` 创建 `FFmpegRTSPPlayer` 并连接信号，调用 `start()` 启动线程。

### 3.4 窗口关闭路径（资源释放顺序）
`closeEvent` 先断开信号连接 → 调用 `player.stop()` 并等待最多 2 秒 →
超时则强制终止线程 → 调用 `video_widget.cleanup()` 释放 GPU 资源（纹理、VAO、VBO、着色器程序）。

---

## 4. 全局约定与陷阱

- **OpenGL 初始化顺序硬性约束**：`QSurfaceFormat` 必须在 `QApplication` 构造之前设置，否则 OpenGL 上下文无法正确创建。`gui/main_window.py` 与 `check.py` 的 `__main__` 块均遵守此约定。

- **QImage 必须 deep copy**：`FFmpegRTSPPlayer` 将 numpy buffer 包装为 `QImage` 后须立即调用 `.copy()`（deep copy），否则 buffer 随栈帧释放后 `QImage` 指向悬空内存。

- **`VideoOpenGLWidget.cleanup()` 需在 GL 上下文内调用**：方法内部调用 `makeCurrent()` 保证上下文激活，调用方（`closeEvent`）需在 widget 仍有效时执行，不能推迟到 `QApplication` 析构阶段。

- **`ui/window_ui.py` 禁止手动编辑**：始终由 `pyside6-uic ui/window.ui -o ui/window_ui.py` 重新生成。






- **`PTZControlClient` 与 `LightControlClient` session 策略不一致**：前者使用持久 `requests.Session`（Keep-Alive），后者每次请求创建新 session。同为 Digest 认证但生命周期管理行为不同。


