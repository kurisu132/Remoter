# VLink 监控终端 — 调试手册

## 硬件与网络拓扑

```
开发机 (Windows)          OrangePi 5 (Ubuntu 22.04 ARM64)
192.168.5.12  ←──网线──→  192.168.5.10
                                │
                                ├──网线──→  摄像头 192.168.1.36:554  (RTSP)
                                ├──网线──→  工控机 192.168.1.11:9000 (UDP)
                                └──USB───→  STM32 /dev/ttyACM0
```

> OrangePi 直连开发机网线后**无法访问外网**，摄像头/工控机走另一块网卡。

---

## 快速启动

```bash
# 正常模式（需要摄像头在线）
uv run python -m gui.main_window

# 离线测试源（FFmpeg 内置 testsrc，无需摄像头）
uv run python -m gui.main_window --test
```

---

## 配置文件（`config.toml`）

项目根目录，直接编辑，重启生效：

```toml
target_ip   = "192.168.1.11"        # 工控机 UDP 目标 IP（UI 连接按钮也会写回此字段）
target_port = 9000

rtsp_url    = "rtsp://192.168.1.36:554/ch01.264"   # 摄像头 RTSP 地址
camera_host = "192.168.1.36"        # 摄像头 HTTP API（PTZ/补光灯）
camera_user = "admin"
camera_pass = "123456"

stm32_port  = "/dev/ttyACM0"        # Windows: "COM3"
```

---

## 各模块独立测试

```bash
uv run python check.py --test              # 端到端冒烟测试（离线）
uv run python check.py                     # 端到端冒烟测试（需摄像头）

uv run python stream/ffmpeg_player.py      # 视频流单独测试（QLabel 显示）
uv run python stream/stm32_reader.py       # STM32 串口读取（需连接硬件）
uv run python stream/udp_control_sender.py # UDP 发送（目标 127.0.0.1:9000）
uv run python gui/opengl_checker.py        # OpenGL 可用性检测
uv run python api/light_control.py         # 补光灯 HTTP 控制
```

---

## 状态指示灯（UI 左下角）

| 指示灯 | 绿 | 黄 | 红 | 灰 |
|---|---|---|---|---|
| RTSP | 正在收流 | 连接中 / 重连倒计时 | — | 停止 |
| STM32 | 收到帧 | — | 串口错误 | 无数据 |
| UDP | 发送正常 | — | 发送出错 | — |
| ESTOP | — | — | 急停激活 | 正常 |
| REMOTE | 遥控激活 | — | — | 未激活 |

---

## 常见问题排查

### 视频不显示 / 黑屏

1. 确认 `config.toml` 中 `rtsp_url` 地址可达：
   ```bash
   ffprobe rtsp://192.168.1.36:554/ch01.264
   ```
2. 先用 `--test` 模式确认 OpenGL 渲染链路正常
3. 查看终端日志中 `[FFmpegRTSPPlayer]` 的输出，重点关注 `FFmpeg exited unexpectedly`
4. OrangePi 上出现 `libGL error: failed to load driver: rockchip` 属**无害警告**，Mesa Panfrost 接管后正常工作

### PTZ 云台不响应

1. 确认 `camera_host` 可 ping 通
2. 独立测试：`uv run python api/ptz_control.py`
3. 检查摄像头 HTTP 端口 80 是否开放：`curl http://192.168.1.36/`
4. 当前实现：`pressed` 发送移动，`released` 发送停止，内部串行队列保证顺序

### STM32 无数据

1. 确认串口路径：Linux `ls /dev/ttyACM*`，Windows 设备管理器查看 COM 口
2. Linux 串口权限：`sudo usermod -aG dialout $USER`（重新登录生效）
3. 修改 `config.toml` 中的 `stm32_port`，无需改代码

### UDP 控制不到工控机

1. 确认 `target_ip` / `target_port` 配置正确
2. UI 底部输入框填入目标 IP 后点"连接"按钮可运行时切换（同时写回 config.toml）
3. 抓包验证：`sudo tcpdump -i eth0 udp port 9000`

### OrangePi 上启动慢（首帧延迟）

- 正常情况：连接成功后约 1-2 秒出首帧
- 如果超过 5 秒：摄像头连接失败触发了重连等待（5 秒倒计时），查看终端 `reconnecting (Ns)` 日志
- 使用 `--test` 确认是否是网络问题还是渲染问题

---

## 日志说明

启动后终端输出各模块日志，前缀为模块名：

```
[FFmpegRTSPPlayer] connecting: rtsp://...
[FFmpegRTSPPlayer] streaming — first frame 14814336 bytes
[MainWindow] RTSP player started
[STM32Reader] port opened: /dev/ttyACM0 @ 115200
[UDPControlSender] target: 192.168.1.11:9000
```

---

## 关键文件索引

| 文件 | 职责 |
|---|---|
| `config.toml` | 所有连接参数（IP、端口、串口路径） |
| `gui/main_window.py` | 应用入口、UI 布局、生命周期 |
| `gui/video_opengl_widget.py` | OpenGL 渲染 |
| `stream/ffmpeg_player.py` | FFmpeg 子进程、帧读取 |
| `stream/stm32_reader.py` | STM32 串口帧解析 |
| `stream/udp_control_sender.py` | UDP 控制帧发送（50 Hz） |
| `api/ptz_control.py` | PTZ 云台 HTTP 控制 |
| `api/light_control.py` | 补光灯 HTTP 控制 |
| `check.py` | 端到端集成冒烟测试 |

---

## 文档体系

| 文件 | 内容 |
|---|---|
| `README.md` | 本文件，面向调试的快速参考 |
| `CLAUDE.md` | 开发环境配置、工作流、Git remote |
| `ARCHITECTURE.md` | 分层架构、数据流、协议格式、全局约定 |
| `LESSONS.md` | 复盘日志，已知陷阱与根因记录 |
