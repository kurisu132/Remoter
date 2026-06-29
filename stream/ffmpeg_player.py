import logging
import shutil
import subprocess as sp
import threading
import time
from typing import Optional

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QImage, QPixmap

logger = logging.getLogger("FFmpegRTSPPlayer")

_RETRY_DELAY = 5   # 断连后重连等待秒数
_PIPE_SZ     = 4 * 1024 * 1024  # OS 管道缓冲目标（4 MB，Linux 专用）
_EMIT_HZ     = 30               # 主线程最大 emit 帧率


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
        self._latest_raw: Optional[bytes] = None
        self._raw_lock   = threading.Lock()
        self.ffmpeg_path = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
        logger.info(f"ffmpeg: {self.ffmpeg_path}")

    # ------------------------------------------------------------------
    def _build_cmd(self) -> list:
        if self.rtsp_url.startswith("test://"):
            return [
                self.ffmpeg_path,
                "-f", "lavfi",
                "-i", f"testsrc=size={self.width}x{self.height}:rate=15",
                "-pix_fmt", "rgb24", "-f", "rawvideo", "-vcodec", "rawvideo",
                "-an", "-sn", "-loglevel", "error", "-",
            ]
        return [
            self.ffmpeg_path,
            "-rtsp_transport", "tcp",
            "-fflags", "nobuffer+discardcorrupt",
            "-flags", "low_delay",
            "-probesize", "2048",
            "-analyzeduration", "1000000",
            "-i", self.rtsp_url,
            "-vf", f"scale={self.width}:{self.height}:flags=fast_bilinear",
            "-sws_flags", "fast_bilinear",
            "-pix_fmt", "rgb24", "-f", "rawvideo", "-vcodec", "rawvideo",
            "-threads", "4", "-thread_type", "slice",
            "-an", "-sn", "-loglevel", "error", "-",
        ]

    # ------------------------------------------------------------------
    def _drain_loop(self, frame_size: int) -> None:
        """以最快速度读取 FFmpeg 管道，只保留最新一帧原始字节。"""
        while self._is_running and self._process:
            data = self._process.stdout.read(frame_size)
            if not data or len(data) != frame_size:
                break
            with self._raw_lock:
                self._latest_raw = data

    def run(self):
        self._is_running = True
        self._stop_event.clear()
        frame_size    = self.width * self.height * 3
        emit_interval = 1.0 / _EMIT_HZ

        while self._is_running:
            self.status_changed.emit("connecting")
            logger.info(f"connecting: {self.rtsp_url}")

            try:
                self._process = sp.Popen(
                    self._build_cmd(),
                    stdout=sp.PIPE,
                    stderr=sp.PIPE,
                    bufsize=frame_size,
                )
                self._try_enlarge_pipe()

                # drain 线程：持续读管道，只保留最新帧
                drain = threading.Thread(
                    target=self._drain_loop, args=(frame_size,), daemon=True
                )
                drain.start()

                first = True
                while self._is_running:
                    t0 = time.monotonic()

                    with self._raw_lock:
                        raw = self._latest_raw
                        self._latest_raw = None

                    if raw:
                        if first:
                            logger.info(f"streaming — first frame {frame_size} bytes")
                            self.status_changed.emit("streaming")
                            first = False
                        q_image = QImage(
                            raw, self.width, self.height,
                            self.width * 3, QImage.Format.Format_RGB888,
                        ).copy()
                        self.frame_updated.emit(q_image)

                    # drain 线程已退出且缓冲为空 → FFmpeg 已停止
                    if not drain.is_alive() and self._latest_raw is None:
                        if self._is_running:
                            err = self._read_stderr()
                            msg = f"FFmpeg exited unexpectedly. {err}".rstrip()
                            logger.error(msg)
                            self.error_occurred.emit(msg)
                        break

                    elapsed = time.monotonic() - t0
                    sleep_t = emit_interval - elapsed
                    if sleep_t > 0:
                        self._stop_event.wait(timeout=sleep_t)

            except Exception as e:
                logger.error(f"FFmpeg error: {e}", exc_info=True)
                if self._is_running:
                    self.error_occurred.emit(str(e))
            finally:
                self._stop_process()

            if not self._is_running or not self._retry:
                break

            # 倒计时重连
            for remaining in range(_RETRY_DELAY, 0, -1):
                if not self._is_running:
                    break
                self.status_changed.emit(f"reconnecting ({remaining}s)")
                self._stop_event.wait(timeout=1)

        self.status_changed.emit("stopped")
        logger.info("player stopped")

    # ------------------------------------------------------------------
    def _try_enlarge_pipe(self):
        try:
            import fcntl
            fcntl.fcntl(self._process.stdout.fileno(), 1031, _PIPE_SZ)
        except Exception:
            pass

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
        """发出停止信号；调用方负责 wait()"""
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
