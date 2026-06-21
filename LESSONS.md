# LESSONS · 判断与复盘日志

> 每条记录一次"预期与实际的落差"。没有落差的不记。
> 历史不回填——从接入这一刻起只记新的，过去流失的让它流失。

## 状态标记
- [新增] — 首次记录，根因/对策已由人确认
- [未验证] — 仅起草，人尚未给出真实判断（不得提炼成永久规则）
- [反复出现] — 同类落差再次发生，低频回顾时优先提拔
- [已提炼→去向] — 已升格为永久规则，注明进了 CLAUDE.md 还是 ARCHITECTURE.md

## 模板
## [日期] 触发场景：一句话
- 预期 vs 实际：我以为 X，结果 Y
- 根因：为什么会有这个落差
- 结论/对策：下次怎么办
- 状态：[新增] / [未验证] / [反复出现] / [已提炼→去向]

---

## [2026-06-21] 重构引入视频管道积压：bufsize 从精确帧大小改为 -1
- 预期 vs 实际：以为 `bufsize=-1`（Python 默认）是中性改动；实际导致 Python 每次只读 8192 字节，需约 1800 次小读才能拼出一帧（14.8 MB），同时新增的 `fcntl` 将 OS 管道扩至 4 MB，允许 FFmpeg 大幅超前写入，帧在管道中持续积压，视频延迟升至 3-5 秒
- 根因：`bufsize` 改前为 `self.width * self.height * 3`（精确 1 帧），改后为 `-1`；commit `3d29c0a`（Jun 14，"feat(ui): 右侧控制面板 + FFmpeg管道优化"）
- 结论/对策：`Popen` 的 `bufsize` 应与单帧字节数对齐，或改为 `0`（无缓冲）；若同时使用 `fcntl` 扩管道，必须确保读取侧速度能跟上写入侧，否则两者叠加会放大积压
- 状态：[未验证]

## [2026-06-21] 重连等待用 time.sleep 在 QThread 中阻塞首帧
- 预期 vs 实际：以为给自动重连加 5 秒等待是无害的用户体验优化；实际 `time.sleep(1)` 在 `QThread.run()` 中同步阻塞，首次连接若有任何抖动就触发，启动延迟链：连接失败（~1s）→ 等待 5s → analyzeduration（1s）≈ 7 秒才出现第一帧
- 根因：commit `7f2dc3a`（Jun 15，"feat: RTSP 自动重连 + 状态指示灯"）新增 `for remaining in range(_RETRY_DELAY, 0, -1): time.sleep(1)`，`_RETRY_DELAY=5`
- 结论/对策：QThread 内的等待应用 `self._stop_event.wait(timeout=1)` 替代 `time.sleep`，支持中断；重连延迟本身合理，但不能用裸 sleep 阻塞线程
- 状态：[未验证]

## [2026-06-21] PTZ 方向命令与 stop 命令的线程竞争导致持续移动
- 预期 vs 实际：以为 pressed/released 绑定 + 各自 `threading.Thread` 能实现"按住移动、松开停止"；实际快速点击（<200ms）时 stop 线程比 move 线程更早完成 HTTP 请求，摄像头收到顺序为 STOP→PAN，停留在移动状态
- 根因：commit `3d29c0a`（Jun 14）引入 `_run_in_thread`，每次 PTZ 调用启动全新线程，无序列化机制；PTZ HTTP 超时 200ms，两个线程在网络层竞争，stop 因请求体更小几乎必然先到
- 结论/对策：PTZ 命令应通过单一串行队列（一个工作线程 + `queue.Queue`）发送，保证 move 入队后 stop 才能入队；或在 move 的 HTTP 完成回调后再发 stop
- 状态：[未验证]

---

## [2026-06-15] 关窗后残留帧信号触发 GL_INVALID_OPERATION 1282
- 预期 vs 实际：以为 `closeEvent` 释放资源后不再有 GL 调用；实际 FFmpeg 线程仍在发 `frame_updated`，`VideoOpenGLWidget` 收到信号后调用已失效的 GL 上下文，触发 1282 错误
- 根因：`closeEvent` 先调用 `stop()` 等待线程退出，但帧信号在 Qt 事件队列里已排好队，线程退出后仍被主线程消费
- 结论/对策：`closeEvent` 必须先 `disconnect` 所有帧信号，再 `stop()/wait()`，顺序不能颠倒
- 状态：[新增]

## [2026-06-15] 阻塞对话框在 OrangePi 上卡死 Qt 事件循环
- 预期 vs 实际：以为连接失败弹 `QMessageBox` 能正常提示用户；实际 OrangePi 上对话框阻塞事件循环，导致整个 UI 卡死，需强制杀进程
- 根因：OrangePi 的 Qt 平台插件对模态对话框的处理与 x86/Windows 不同，事件泵被卡住
- 结论/对策：连接状态改为非阻塞圆点指示灯 + 后台自动重连（`_RETRY_DELAY` 秒），永远不用 `QMessageBox` 阻塞主线程
- 状态：[新增]

## [2026-06-15] 硬编码串口路径跨平台失效
- 预期 vs 实际：以为 `/dev/ttyACM0` 在开发机（Windows）和 OrangePi（Linux）都能用；实际 Windows 串口为 `COMx`，路径格式完全不同
- 根因：串口路径是平台相关字符串，直接写死在代码里无法跨平台
- 结论/对策：串口路径移入 `~/.vlink/config.json`（`stm32_port` 字段），代码只读 config，不再硬编码；Windows 改 config 即可，无需改代码
- 状态：[新增]
