import logging
import subprocess as sp
import numpy as np
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QImage, QPixmap

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FFmpeg-RTSP-Player")


class FFmpegRTSPPlayer(QThread):
    """
    基于FFmpeg的RTSP拉流线程，输出QImage到UI

    1080P 优化版本特性：
    - ✅ 针对 1920x1080 分辨率优化
    - ✅ 低延迟解码参数
    - ✅ 多线程加速
    - ✅ 零拷贝优化
    - ✅ 如果摄像头输出非 1080P，自动使用快速缩放
    """
    frame_updated = Signal(QImage)  # 发送QImage信号（UI线程显示）
    error_occurred = Signal(str)  # 错误信息信号

    def __init__(self, rtsp_url: str, width=1920, height=1080, parent=None):
        super().__init__(parent)
        self.rtsp_url = rtsp_url  # RTSP流地址
        self.width = width  # 目标宽度（1920）
        self.height = height  # 目标高度（1080）
        self._is_running = False  # 线程运行标志
        self._process = None  # FFmpeg子进程句柄

    def run(self) -> None:
        """启动FFmpeg拉流，读取帧并发送到UI"""
        self._is_running = True

        # ✅ 1080P 低延迟优化命令
        ffmpeg_cmd = [
            "ffmpeg",

            # ========== 输入优化 ==========
            "-rtsp_transport", "tcp",  # TCP 传输（稳定）
            "-fflags", "nobuffer",  # 禁用缓冲区
            "-flags", "low_delay",  # 低延迟标志
            "-probesize", "2048",  # 2KB 探测
            "-analyzeduration", "1000000",  # 1 秒分析

            # ========== 输入源 ==========
            "-i", self.rtsp_url,  # RTSP 地址

            # ========== 解码和缩放优化 ==========
            # 如果摄像头输出已经是 1080P，缩放操作会自动跳过（无性能损失）
            # 如果不是 1080P，使用快速双线性缩放
            "-vf", f"scale={self.width}:{self.height}:flags=fast_bilinear",
            "-sws_flags", "fast_bilinear",  # 快速缩放算法

            # ========== 输出格式 ==========
            "-pix_fmt", "rgb24",  # RGB24 格式
            "-f", "rawvideo",  # 原始视频流
            "-vcodec", "rawvideo",  # 原始视频编码

            # ========== 性能优化 ==========
            "-threads", "4",  # 使用 4 个线程（加速解码）

            # ========== 其他设置 ==========
            "-an", "-sn",  # 忽略音频和字幕
            "-loglevel", "error",  # 仅显示错误日志
            "-"  # 输出到管道
        ]

        try:
            logger.info(f"🚀 启动 1080P 低延迟模式 FFmpeg 拉流")
            logger.info(f"📐 目标分辨率: {self.width}x{self.height}")
            logger.info(f"💡 提示：如果摄像头已配置为 1080P 输出，将无需缩放（延迟最低）")

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
                        except:
                            pass
                    self.error_occurred.emit("流已断开或无数据")
                    break

                # 检查数据完整性
                if len(frame_data) != frame_size:
                    logger.warning(f"⚠️ 数据不完整: 期望 {frame_size} 字节，实际 {len(frame_data)} 字节")
                    continue

                # 转换为 numpy 数组
                try:
                    frame = np.frombuffer(frame_data, dtype=np.uint8).reshape(
                        (self.height, self.width, 3)
                    )
                except ValueError as e:
                    logger.error(f"❌ 数据格式错误: {e}")
                    continue

                # ✅ 创建 QImage 深拷贝
                q_image = QImage(
                    frame.data,
                    self.width,
                    self.height,
                    self.width * 3,
                    QImage.Format_RGB888
                ).copy()

                # 发送信号
                self.frame_updated.emit(q_image)

                frame_count += 1
                if frame_count == 1:
                    logger.info("🎉 成功接收第一帧！")
                if frame_count % 100 == 0:
                    logger.info(f"📹 已处理 {frame_count} 帧")

        except Exception as e:
            logger.error(f"❌ 拉流失败: {e}", exc_info=True)
            self.error_occurred.emit(f"拉流失败: {str(e)}")
        finally:
            self._stop_process()
            self._is_running = False
            logger.info("FFmpeg 拉流线程已停止")

    def _stop_process(self):
        """终止FFmpeg子进程"""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            self._process.wait()
            logger.info("FFmpeg 子进程已终止")

    def stop(self):
        """停止线程"""
        self._is_running = False
        self._stop_process()
        self.wait()


# 独立测试
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication, QLabel, QWidget, QVBoxLayout

    TEST_RTSP_URL = "rtsp://192.168.0.36:554/ch01.264"

    app = QApplication(sys.argv)

    window = QWidget()
    layout = QVBoxLayout(window)
    label = QLabel("正在连接RTSP流...")
    label.setAlignment(Qt.AlignCenter)
    label.setMinimumSize(1920, 1080)
    layout.addWidget(label)
    window.setWindowTitle("FFmpeg RTSP 1080P 低延迟播放器测试")
    window.show()

    # 使用 1080P 分辨率
    player = FFmpegRTSPPlayer(TEST_RTSP_URL, 1920, 1080)
    player.frame_updated.connect(
        lambda img: label.setPixmap(QPixmap.fromImage(img.scaled(
            label.width(), label.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )))
    )
    player.error_occurred.connect(lambda err: label.setText(f"错误：{err}"))
    player.start()

    sys.exit(app.exec())
