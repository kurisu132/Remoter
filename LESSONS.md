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
- 状态：[已提炼→CLAUDE.md 视频管道关键约束]

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

---

## [2026-06-29] drain 线程和 QTimer 延迟上传无法解决 TCP 管道积压

- 预期 vs 实际：以为让一个 drain 线程以最快速度读取 FFmpeg stdout、主循环再以固定帧率取最新帧，能跳过积压的旧帧降低延迟；实际 drain 线程读取速度与 FFmpeg 解码速度相同（FFmpeg 写入才是瓶颈），drain 只是把阻塞从主线程挪到了辅助线程，帧仍然按 FIFO 顺序出来，无法跳过。同样，QTimer 延迟 GL 上传只增加约 33ms 延迟，没有降低端到端延迟的任何作用
- 根因：TCP 管道是 FIFO，即使读取再快也只能消费 FFmpeg 已解码的帧；"跳帧"需要在解码之前丢弃，而不是在解码之后选择
- 结论/对策：只需一个最简单的 `stdout.read(frame_size)` 阻塞循环，不需要 drain 线程或 QTimer；帧率不够时根因是解码速度跟不上摄像头发送速率，需从摄像头配置或硬件解码入手，不是管道读取策略
- 状态：[新增]

## [2026-06-29] OrangePi A76 软解 5MP H264 速度上限约 10fps，低于摄像头发送速率 15fps

- 预期 vs 实际：以为优化 FFmpeg 参数（nobuffer、low_delay、probesize）就能把延迟降到可接受范围；实际无论参数怎么调，OrangePi 软解 2592×1904 H264 的速度上限约 10fps，而摄像头以 15fps 发送，TCP 缓冲区每秒净积压 5 帧，运行 20s 后积压达 6-7s，调参只能影响首帧延迟，无法消除积压增长
- 根因：ARM Cortex-A76 单核算力约为 x86 Zen3 的 40-60%，x86 上软解 5MP H264 轻松 40-60fps，OrangePi 只能 10fps；这是 CPU 算力的硬性上限，FFmpeg 参数调不了
- 结论/对策：降低摄像头分辨率（720P 软解可达 30fps）是权宜之计；根治方案是使用 RK3588 内置 VPU 硬件解码（h264_rkmpp），可将 5MP 解码耗时从 ~100ms 降至 <10ms，彻底消除积压
- 状态：[新增]

## [2026-06-29] UDP RTSP 在局域网直连下仍有丢包导致 RGB24 管道字节错位

- 预期 vs 实际：以为以太网直连两台设备不会丢包，切换 UDP 传输只有延迟优势；实际偶发 UDP 丢包后 H264 解码器仍输出一帧数据（错误数据），导致 RGB24 stdout 字节流偏移，后续每一帧颜色通道全错（全绿 / 撕裂），且会持续直到 FFmpeg 重连
- 根因：UDP 无重传，FFmpeg 用错误数据解码并写入 stdout，`stdout.read(frame_size)` 读到的字节跨越了两帧边界，没有帧边界标记无法同步
- 结论/对策：对本应用（RGB24 裸帧管道）而言必须使用 TCP 传输，TCP 的顺序保证使字节流不会错位；若需降低延迟，靠 `-max_delay 0` 和 `-analyzeduration 100000` 压缩 FFmpeg 内部缓冲，而不是切 UDP
- 状态：[新增]

## [2026-06-29] h264_rkmpp 已内置于 OrangePi 系统 ffmpeg，无需另装

- 预期 vs 实际：以为 RK3588 MPP 硬件解码需要安装 `ffmpeg-rockchip` 或从源码编译；实际 `ffmpeg -codecs | grep h264` 确认 `h264_rkmpp` 已作为解码器选项存在于 `/usr/bin/ffmpeg`，可直接用 `-c:v h264_rkmpp` 启用，`ffmpeg -hwaccels` 虽然没列出 rkmpp 但解码器本身可用
- 根因：OrangePi 官方镜像的 ffmpeg 包已经预编译了 Rockchip MPP 支持
- 结论/对策：硬件解码实现只需在 `_build_cmd()` 加 `-c:v h264_rkmpp`（Linux 平台），FFmpeg 遇到软件 scale 滤镜会自动插入 hwdownload + NV12 转换，无需额外处理；若出现 `Impossible to convert`，则显式写 `-vf "hwdownload,format=nv12,scale=..."` 
- 状态：[新增]
