# -*- coding: utf-8 -*-
import subprocess as sp
import numpy as np
from PySide6.QtCore import QThread, Signal
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FFmpeg-RTSP-Player")

class FFmpegRTSPPlayer(QThread):
    """
    FFmpeg 拉流线程
    输出 numpy.ndarray RGB 帧
    """
    frame_ready = Signal(np.ndarray)
    error_occurred = Signal(str)

    def __init__(self, rtsp_url: str, width=1280, height=720, parent=None):
        super().__init__(parent)
        self.rtsp_url = rtsp_url
        self.width = width
        self.height = height
        self._is_running = False
        self._process = None

    def run(self):
        self._is_running = True
        ffmpeg_cmd = [
            "ffmpeg",
            "-rtsp_transport", "tcp",
            "-i", self.rtsp_url,
            "-pix_fmt", "rgb24",
            "-s", f"{self.width}x{self.height}",
            "-f", "rawvideo",
            "-an", "-sn",
            "-vcodec", "rawvideo",
            "-flags", "low_delay",
            "-fflags", "nobuffer",
            "-loglevel", "error",
            "-"
        ]
        try:
            self._process = sp.Popen(
                ffmpeg_cmd,
                stdout=sp.PIPE,
                stderr=sp.PIPE,
                bufsize=self.width*self.height*3
            )
            frame_size = self.width*self.height*3
            while self._is_running:
                raw = self._process.stdout.read(frame_size)
                if not raw:
                    self.error_occurred.emit("视频流断开或无数据")
                    break
                frame = np.frombuffer(raw, dtype=np.uint8).reshape((self.height, self.width,3))
                self.frame_ready.emit(frame)
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            self._stop_process()
            self._is_running = False
            logger.info("FFmpeg线程结束")

    def _stop_process(self):
        if self._process and self._process.poll() is None:
            self._process.terminate()
            self._process.wait()

    def stop(self):
        self._is_running = False
        self._stop_process()
        self.wait()
