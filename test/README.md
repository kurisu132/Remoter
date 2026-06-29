# test/ — 硬件模拟脚本

```
test/
├── sim_stm32.py   # 模拟 STM32 摇杆，向主应用发送串口控制帧（OrangePi 用）
└── sim_target.py  # 模拟工控机，接收并解析主应用发出的 UDP 控制帧
```

## 各脚本的验证范围

| 脚本 | 验证内容 | 推荐平台 |
|---|---|---|
| `sim_target.py` | UDP 帧格式、校验和、50 Hz 频率、数值透传 | Windows / OrangePi 均可 |
| `sim_stm32.py` | STM32 串口帧解析、完整控制链路端到端 | **OrangePi**（配合 socat） |

> **Windows 开发机**：直接跑 `sim_target.py` 即可验证 UDP 输出，无需虚拟串口。  
> **完整链路测试**（含串口解析）在 OrangePi 上做，用 socat 建虚拟串口对。

---

## sim_target.py — 验证 UDP 输出（Windows / OrangePi）

主应用无 STM32 输入时以默认值 `(0, 0)` 持续发 50 Hz，`sim_target.py` 即可收到并验证格式。

```bash
# 终端 1：启动模拟器
uv run python test/sim_target.py

# 终端 2：启动主应用（无需真实摄像头）
uv run python -m gui.main_window --test
```

可选参数：
```bash
uv run python test/sim_target.py --port 9000 --bind 0.0.0.0
```

---

## sim_stm32.py — 完整链路测试（OrangePi）

### 前置：修改 config.toml

```toml
stm32_port = "/tmp/stm32_app"
target_ip  = "127.0.0.1"        # 本机测试改为 loopback，实机部署改回 192.168.1.11
```

### 启动

```bash
# 终端 1：UDP 接收器
uv run python test/sim_target.py

# 终端 2：STM32 模拟器（--pty 自动建虚拟串口，无需 socat）
uv run python test/sim_stm32.py --pty

# 终端 3：主应用
uv run python -m gui.main_window
```

`--pty` 会在 `/tmp/stm32_app` 创建软链接，主应用直接从那里读帧。退出时自动清理软链接。

### 发送模式

| 模式 | 说明 | 示例 |
|---|---|---|
| `sine`（默认）| left/right 按正弦曲线连续变化 | `--mode sine` |
| `static` | 固定值 | `--mode static --left 100 --right 100` |
| `walk` | 预设序列：静止→直行→左转→直行→停止 | `--mode walk` |

附加标志：
```bash
--estop       # 置 ESTOP 位，触发紧急停止
--no-active   # 清除 REMOTE_ACTIVE 位（默认已置位）
--rate 50     # 发送频率 Hz（默认 50）
```

---

## 日志示例

**sim_stm32.py：**
```
[STM32 模拟器] 串口 /tmp/stm32_sim @115200  模式=sine  频率=50 Hz
[10:23:45.012] 发送 #0001  left=+000  right=+000  flags=0x02 (REMOTE_ACTIVE)
[10:23:45.032] 发送 #0002  left=+025  right=+025  flags=0x02 (REMOTE_ACTIVE)
```

**sim_target.py：**
```
[UDP 接收器] 监听 0.0.0.0:9000 ...
[10:23:45.022]  left=+000  right=+000  flags=0x02 (REMOTE_ACTIVE)          ✓
[10:23:50.000] 统计 5.0s: 收到 247 帧 / 坏帧 0 / 均频 49.4 Hz
```

`✓` 校验和正确，`✗ BAD` 表示校验和错误，每 5 秒自动打印频率统计。

---

## 协议速查

**STM32 帧（串口，9 字节）**
```
[0xAB][0x01][0x05][left_lo][left_hi][right_lo][right_hi][flags][checksum]
```

**UDP 帧（REMOTE_PROTOCOL_v1，8 字节）**
```
[0x12][0x10][left_lo][left_hi][right_lo][right_hi][flags][checksum]
```

`left` / `right`：int16 小端序，`[-255, +255]`；`flags`：bit0=ESTOP，bit1=REMOTE_ACTIVE；`checksum`：前 N-1 字节之和 mod 256。
