import logging
import subprocess as sp
import shutil
import numpy as np
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QImage, QPixmap

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FFmpeg-RTSP-Player")


class FFmpegRTSPPlayer(QThread):
    """
    基于FFmpeg的RTSP拉流线程，输出QImage到UI

    Ubuntu 专用 5MP 多线程优化版本特性：
    - ✅ 自动检测 FFmpeg 路径（Ubuntu 系统路径）
    - ✅ 针对 2592x1904 (5MP) 分辨率优化
    - ✅ 多线程slice级并行解码（4线程）
    - ✅ 低延迟解码参数
    - ✅ 零拷贝优化
    - ✅ 适配更高码率和分辨率
    """
    frame_updated = Signal(QImage)  # 发送QImage信号（UI线程显示）
    error_occurred = Signal(str)  # 错误信息信号

    def __init__(self, rtsp_url: str, width=2592, height=1904, parent=None):
        super().__init__(parent)
        self.rtsp_url = rtsp_url  # RTSP流地址
        self.width = 2592  # 目标宽度（2592）
        self.height = 1904  # 目标高度（1904）
        self._is_running = False  # 线程运行标志
        self._process = None  # FFmpeg子进程句柄

        # ✅ Ubuntu：自动检测 FFmpeg 路径
        self.ffmpeg_path = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
        logger.info(f"✅ FFmpeg 路径: {self.ffmpeg_path}")

    def run(self) -> None:
        """启动FFmpeg拉流，读取帧并发送到UI"""
        self._is_running = True

        # ✅ 5MP 多线程优化命令（Ubuntu）
        ffmpeg_cmd = [
            self.ffmpeg_path,  # ✅ 使用检测到的 FFmpeg 路径

            # ========== 输入优化 ==========
            "-rtsp_transport", "tcp",  # TCP 传输（稳定）
            "-fflags", "nobuffer",  # 禁用缓冲区
            "-flags", "low_delay",  # 低延迟标志
            "-probesize", "2048",  # 2KB 探测（适应更大分辨率）
            "-analyzeduration", "1000000",  # 1 秒分析（适应更高码率）

            # ========== 输入源 ==========
            "-i", self.rtsp_url,  # RTSP 地址

            # ========== 解码和缩放优化 ==========
            # 如果摄像头输出已经是 5MP，缩放操作会自动跳过（无性能损失）
            # 如果不是 5MP，使用快速双线性缩放
            "-vf", f"scale={self.width}:{self.height}:flags=fast_bilinear",
            "-sws_flags", "fast_bilinear",  # 快速缩放算法

            # ========== 输出格式 ==========
            "-pix_fmt", "rgb24",  # RGB24 格式
            "-f", "rawvideo",  # 原始视频流
            "-vcodec", "rawvideo",  # 原始视频编码

            # ========== 5MP 性能优化关键：多线程解码 ==========
            "-threads", "4",  # 使用 4 个线程（加速解码）
            "-thread_type", "slice",  # slice 级别并行（最适合 H.264）

            # ========== 其他设置 ==========
            "-an", "-sn",  # 忽略音频和字幕
            "-loglevel", "error",  # 仅显示错误日志
            "-"  # 输出到管道
        ]

        try:
            logger.info(f"🚀 启动 5MP 多线程低延迟模式 FFmpeg 拉流")
            logger.info(f"📐 目标分辨率: {self.width}x{self.height}")
            logger.info(f"🧵 多线程解码: 4 线程 (slice 级并行)")
            logger.info(f"💡 提示：摄像头应配置为 2592x1904@15-20fps，码率 6000-8000Kbps")

            # 启动FFmpeg子进程
            self._process = sp.Popen(
                ffmpeg_cmd,
                stdout=sp.PIPE,
                stderr=sp.PIPE,
                bufsize=self.width * self.height * 3  # 缓冲区 = 1帧大小
            )

            frame_size = self.width * self.height * 3  # 每帧字节数（RGB24）
            frame_count = 0

            logger.info("✅ FFmpeg 进程已启动，开始接收视频流...")

            while self._is_running:
                # 读取一帧数据
                frame_data = self._process.stdout.read(frame_size)
                if not frame_data:
                    logger.error("❌ 未接收到数据")
                    # 读取错误信息
                    if self._process.stderr:
                        try:
                            error_msg = self._process.stderr.read(1024).decode('utf-8', errors='ignore')
                            if error_msg:
                                logger.error(f"FFmpeg 错误: {error_msg}")
                                self.error_occurred.emit(error_msg)
                        except Exception as e:
                            logger.error(f"读取错误信息失败: {e}")
                    break

                # ✅ 日志优化：只在首次接收和特殊情况下记录
                if frame_count == 0:
                    logger.info(f"✅ 首次接收到 5MP 帧数据（{len(frame_data)} 字节）")

                # 检查数据完整性
                if len(frame_data) != frame_size:
                    logger.warning(f"⚠️ 数据不完整: 期望 {frame_size} 字节，实际 {len(frame_data)} 字节")
                    continue

                try:
                    # 转换为numpy数组（零拷贝）
                    frame_array = np.frombuffer(frame_data, dtype=np.uint8)
                    frame_array = frame_array.reshape((self.height, self.width, 3))

                    # 转换为QImage（内存安全）
                    q_image = QImage(
                        frame_array.data,
                        self.width,
                        self.height,
                        self.width * 3,
                        QImage.Format_RGB888
                    )

                    # ✅ 关键修复：深拷贝防止崩溃
                    q_image = q_image.copy()

                    # 发射信号到UI线程
                    self.frame_updated.emit(q_image)
                    frame_count += 1

                except ValueError as e:
                    logger.error(f"❌ 数据格式错误: {e}")
                    continue

        except Exception as e:
            logger.error(f"❌ FFmpeg 拉流异常: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
        finally:
            self._stop_process()
            logger.info("🛑 FFmpeg 拉流已停止")

    def _stop_process(self):
        """停止 FFmpeg 子进程"""
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
                logger.info("✅ FFmpeg 子进程已终止")
            except Exception as e:
                logger.warning(f"⚠️ 强制结束 FFmpeg 子进程: {e}")
                self._process.kill()

    def stop(self):
        """停止线程"""
        logger.info("📴 请求停止拉流...")
        self._is_running = False
        self._stop_process()
        self.wait()  # 等待线程结束
        logger.info("✅ 拉流线程已停止")


# ========== 独立测试 ==========
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication, QLabel
    from PySide6.QtCore import Qt

    app = QApplication(sys.argv)

    # 创建显示窗口
    label = QLabel()
    label.setWindowTitle("FFmpeg RTSP Player Ubuntu 测试 (5MP)")
    label.setAlignment(Qt.AlignCenter)
    label.resize(1280, 960)  # 显示窗口（5MP 按比例缩小）
    label.show()

    # 启动播放器
    rtsp_url = "rtsp://192.168.0.36:554/ch01.264"  # 替换为你的RTSP地址
    player = FFmpegRTSPPlayer(rtsp_url, width=2592, height=1904)


    # 连接信号
    def update_label(q_image):
        """更新 QLabel 显示"""
        pixmap = QPixmap.fromImage(q_image)
        # 缩放到窗口大小
        pixmap = pixmap.scaled(
            label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        label.setPixmap(pixmap)


    player.frame_updated.connect(update_label)
    player.error_occurred.connect(lambda msg: print(f"❌ 错误: {msg}"))

    # 启动播放
    player.start()

    # 运行应用
    try:
        sys.exit(app.exec())
    finally:
        player.stop()
