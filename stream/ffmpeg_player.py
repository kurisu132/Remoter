import logging
import shutil
import subprocess as sp
import threading
import time
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QImage, QPixmap

logger = logging.getLogger("FFmpegRTSPPlayer")

_RETRY_DELAY = 5   # 断连后重连等待秒数


class FFmpegRTSPPlayer(QThread):
    frame_updated  = Signal(QImage)
    error_occurred = Signal(str)
    status_changed = Signal(str)   # "connecting" | "streaming" | "reconnecting (Ns)" | "stopped"

    def __init__(self, rtsp_url: str, width: int = 2592, height: int = 1904, parent=None):
        super().__init__(parent)
        self.rtsp_url    = rtsp_url
        self.width       = width
        self.height      = height
        self._is_running  = False
        self._process     = None
        self._retry       = not rtsp_url.startswith("test://")
        self._stop_event  = threading.Event()
        self.ffmpeg_path = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
        logger.info(f"ffmpeg: {self.ffmpeg_path}")

    def _build_cmd(self) -> list:
        if self.rtsp_url.startswith("test://"):
            return [
                self.ffmpeg_path,
                "-f", "lavfi",
                "-i", f"testsrc=size={self.width}x{self.height}:rate=15",
                "-pix_fmt", "rgb24", "-f", "rawvideo", "-vcodec", "rawvideo",
                "-an", "-sn", "-loglevel", "error", "-",
            ]
        import sys
        # OrangePi/Linux: 使用 RK3588 VPU 硬解，避免 ARM 软解速度不足导致 TCP 积压
        hw_decoder = ["-c:v", "h264_rkmpp"] if sys.platform != "win32" else []
        return [
            self.ffmpeg_path,
            "-rtsp_transport", "tcp",
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-max_delay", "0",
            "-probesize", "2048",
            "-analyzeduration", "100000",
            *hw_decoder,
            "-i", self.rtsp_url,
            "-vf", f"scale={self.width}:{self.height}:flags=fast_bilinear",
            "-sws_flags", "fast_bilinear",
            "-pix_fmt", "rgb24", "-f", "rawvideo", "-vcodec", "rawvideo",
            "-threads", "4", "-thread_type", "slice",
            "-an", "-sn", "-loglevel", "error", "-",
        ]

    def run(self):
        self._is_running = True
        self._stop_event.clear()
        frame_size = self.width * self.height * 3

        while self._is_running:
            self.status_changed.emit("connecting")
            logger.info(f"connecting: {self.rtsp_url}")

            try:
                self._process = sp.Popen(
                    self._build_cmd(),
                    stdout=sp.PIPE,
                    stderr=sp.PIPE,
                    bufsize=frame_size,   # 必须等于 frame_size，不可改为 -1 或更大值。
                                      # 背压机制：pipe 只容 1 帧，FFmpeg 写满即阻塞，
                                      # 强制解码速率跟随消费速率，防止帧堆积延迟暴涨。
                                      # 改为 -1 的后果：延迟从 ~500ms 线性增长到数秒（2026-06 已验证）。
                )

                first = True
                frame_count = 0
                t_window = time.monotonic()
                while self._is_running:
                    t_read_start = time.monotonic()
                    raw = self._process.stdout.read(frame_size)
                    t_read_end = time.monotonic()

                    if not raw:
                        break
                    if len(raw) != frame_size:
                        continue

                    frame_count += 1
                    decode_ms = (t_read_end - t_read_start) * 1000

                    if first:
                        logger.info(f"streaming — first frame {frame_size} bytes, "
                                    f"first-frame latency {decode_ms:.0f} ms")
                        self.status_changed.emit("streaming")
                        first = False
                        t_window = t_read_end

                    # 每 30 帧报一次实际帧率和单帧解码耗时
                    if frame_count % 30 == 0:
                        elapsed = t_read_end - t_window
                        fps = 30 / elapsed if elapsed > 0 else 0
                        logger.info(f"[perf] decoded {frame_count} frames  "
                                    f"fps={fps:.1f}  last_decode={decode_ms:.0f}ms")
                        t_window = t_read_end

                    q_image = QImage(
                        raw, self.width, self.height,
                        self.width * 3, QImage.Format.Format_RGB888,
                    ).copy()
                    self.frame_updated.emit(q_image)

                if self._is_running:
                    err = self._read_stderr()
                    msg = f"FFmpeg exited unexpectedly. {err}".rstrip()
                    logger.error(msg)
                    self.error_occurred.emit(msg)

            except Exception as e:
                logger.error(f"FFmpeg error: {e}", exc_info=True)
                if self._is_running:
                    self.error_occurred.emit(str(e))
            finally:
                self._stop_process()

            if not self._is_running or not self._retry:
                break

            for remaining in range(_RETRY_DELAY, 0, -1):
                if not self._is_running:
                    break
                self.status_changed.emit(f"reconnecting ({remaining}s)")
                self._stop_event.wait(timeout=1)

        self.status_changed.emit("stopped")
        logger.info("player stopped")

    def _read_stderr(self) -> str:
        try:
            return self._process.stderr.read(2048).decode("utf-8", errors="ignore").strip()
        except Exception:
            return ""

    def _stop_process(self):
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                self._process.kill()
            self._process = None

    def stop(self):
        self._is_running = False
        self._stop_event.set()
        self._stop_process()


# ========== 独立测试 ==========
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication, QLabel

    logging.basicConfig(level=logging.INFO)
    app = QApplication(sys.argv)

    label = QLabel()
    label.setWindowTitle("FFmpegRTSPPlayer 独立测试")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.resize(1280, 960)
    label.show()

    url = "rtsp://192.168.1.36:554/ch01.264"
    player = FFmpegRTSPPlayer(url, width=2592, height=1904)

    def on_frame(q_image: QImage):
        pixmap = QPixmap.fromImage(q_image).scaled(
            label.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        label.setPixmap(pixmap)

    player.frame_updated.connect(on_frame)
    player.status_changed.connect(lambda s: print(f"[status] {s}"))
    player.error_occurred.connect(lambda m: print(f"[error] {m}"))
    player.start()

    try:
        sys.exit(app.exec())
    finally:
        player.stop()
        player.wait(3000)
