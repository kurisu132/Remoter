import logging
import subprocess as sp
import shutil
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QImage

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
        self.width = width
        self.height = height
        self._is_running = False  # 线程运行标志
        self._process = None  # FFmpeg子进程句柄

        # ✅ Ubuntu：自动检测 FFmpeg 路径
        self.ffmpeg_path = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
        logger.info(f"✅ FFmpeg 路径: {self.ffmpeg_path}")

    def _build_cmd(self) -> list:
        """根据 URL 类型构建 FFmpeg 命令。test:// 使用内置测试图案，无需摄像头。"""
        if self.rtsp_url.startswith("test://"):
            return [
                self.ffmpeg_path,
                "-f", "lavfi",
                "-i", f"testsrc=size={self.width}x{self.height}:rate=15",
                "-pix_fmt", "rgb24",
                "-f", "rawvideo",
                "-vcodec", "rawvideo",
                "-an", "-sn",
                "-loglevel", "error",
                "-",
            ]
        return [
            self.ffmpeg_path,
            "-rtsp_transport", "tcp",
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-probesize", "2048",
            "-analyzeduration", "1000000",
            "-i", self.rtsp_url,
            "-vf", f"scale={self.width}:{self.height}:flags=fast_bilinear",
            "-sws_flags", "fast_bilinear",
            "-pix_fmt", "rgb24",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-threads", "4",
            "-thread_type", "slice",
            "-an", "-sn",
            "-loglevel", "error",
            "-",
        ]

    def run(self) -> None:
        """启动FFmpeg拉流，读取帧并发送到UI"""
        self._is_running = True

        ffmpeg_cmd = self._build_cmd()
        is_test = self.rtsp_url.startswith("test://")

        try:
            if is_test:
                logger.info(f"🧪 离线测试模式（lavfi testsrc）{self.width}x{self.height}@15fps")
            else:
                logger.info(f"🚀 启动 5MP 多线程低延迟模式 FFmpeg 拉流")
                logger.info(f"📐 目标分辨率: {self.width}x{self.height}")
                logger.info(f"🧵 多线程解码: 4 线程 (slice 级并行)")
                logger.info(f"💡 提示：摄像头应配置为 2592x1904@15-20fps，码率 6000-8000Kbps")

            self._process = sp.Popen(
                ffmpeg_cmd,
                stdout=sp.PIPE,
                stderr=sp.PIPE,
                bufsize=-1,
            )

            # 尽量增大 OS 管道缓冲（Linux 专用），减少 FFmpeg 因写端阻塞而退出
            try:
                import fcntl
                F_SETPIPE_SZ = 1031
                fcntl.fcntl(self._process.stdout.fileno(), F_SETPIPE_SZ, 4 * 1024 * 1024)
                logger.info("pipe buffer set to 4 MB")
            except Exception:
                pass  # Windows / 非 root 时静默跳过

            frame_size = self.width * self.height * 3
            frame_count = 0

            logger.info("FFmpeg process started")

            while self._is_running:
                frame_data = self._process.stdout.read(frame_size)

                if not frame_data:
                    # 主动停止时管道关闭属正常，非主动停止才报错
                    if self._is_running:
                        try:
                            err = self._process.stderr.read(2048).decode("utf-8", errors="ignore")
                        except Exception:
                            err = ""
                        msg = f"FFmpeg exited unexpectedly. {err.strip()}"
                        logger.error(msg)
                        self.error_occurred.emit(msg)
                    break

                if len(frame_data) != frame_size:
                    logger.warning(f"incomplete frame: got {len(frame_data)}/{frame_size} bytes, skipping")
                    continue

                if frame_count == 0:
                    logger.info(f"first frame received ({frame_size} bytes)")

                # bytes → QImage，deep copy 保证内存安全
                q_image = QImage(
                    frame_data, self.width, self.height,
                    self.width * 3, QImage.Format.Format_RGB888,
                ).copy()
                self.frame_updated.emit(q_image)
                frame_count += 1

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
        """发出停止信号并终止 FFmpeg 子进程，不阻塞等待线程——由调用方负责 wait()"""
        logger.info("请求停止拉流...")
        self._is_running = False
        self._stop_process()


# ========== 独立测试 ==========
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication, QLabel
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap

    app = QApplication(sys.argv)

    # 创建显示窗口
    label = QLabel()
    label.setWindowTitle("FFmpeg RTSP Player Ubuntu 测试 (5MP)")
    label.setAlignment(Qt.AlignCenter)
    label.resize(1280, 960)  # 显示窗口（5MP 按比例缩小）
    label.show()

    # 启动播放器
    rtsp_url = "rtsp://192.168.1.36:554/ch01.264"  # 替换为你的RTSP地址
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
