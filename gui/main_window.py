"""
MainWindow — Phase 1 控制框架

布局：
  ┌──────────────────────────────────┐
  │        VideoOpenGLWidget         │  ← 占满剩余空间
  ├──────────────────────────────────┤
  │ STM32:● UDP:● ESTOP:○ R-ACT:○  IP:[___________] [连接] │  ← 状态栏
  └──────────────────────────────────┘

依赖关系（仅 Phase 1）：
  stream/ffmpeg_player.py   — 视频流
  stream/stm32_reader.py    — STM32 串口输入
  stream/udp_control_sender.py — UDP 控制发送
  gui/video_opengl_widget.py — OpenGL 渲染
"""
import logging
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QSurfaceFormat
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gui.video_opengl_widget import VideoOpenGLWidget
from stream.ffmpeg_player import FFmpegRTSPPlayer
from stream.stm32_reader import ControlFrame, STM32Reader
from stream.udp_control_sender import UDPControlSender, load_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MainWindow")

RTSP_URL   = "rtsp://192.168.1.36:554/ch01.264"
FRAME_W    = 2592
FRAME_H    = 1904
STM32_PORT = "/dev/ttyACM0"

# 状态指示颜色
_GREEN = "color: #00cc44; font-size: 16px;"
_RED   = "color: #ff3333; font-size: 16px;"
_GRAY  = "color: #888888; font-size: 16px;"


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()
        self._start_rtsp()
        self._start_stm32()
        self._start_udp_sender()
        self.resize(1280, 800)
        self.setWindowTitle("VLink 监控终端")
        logger.info("MainWindow initialized")

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 视频区 ──
        self.video_widget = VideoOpenGLWidget()
        self.video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self.video_widget)

        # ── 状态栏 ──
        bar = QWidget()
        bar.setFixedHeight(44)
        bar.setStyleSheet("background: #1a1a1a;")
        h = QHBoxLayout(bar)
        h.setContentsMargins(12, 0, 12, 0)
        h.setSpacing(20)

        self._lbl_stm32  = self._dot_label("STM32")
        self._lbl_udp    = self._dot_label("UDP")
        self._lbl_estop  = self._dot_label("ESTOP")
        self._lbl_remote = self._dot_label("REMOTE")
        for w in (self._lbl_stm32, self._lbl_udp, self._lbl_estop, self._lbl_remote):
            h.addWidget(w)

        h.addStretch()

        lbl_ip = QLabel("目标 IP:")
        lbl_ip.setStyleSheet("color: #cccccc;")
        h.addWidget(lbl_ip)

        cfg = load_config()
        self._ip_edit = QLineEdit(cfg.get("target_ip", "192.168.1.11"))
        self._ip_edit.setFixedWidth(140)
        self._ip_edit.setStyleSheet(
            "background:#2a2a2a; color:#ffffff; border:1px solid #555; padding:2px 6px;"
        )
        h.addWidget(self._ip_edit)

        btn = QPushButton("连接")
        btn.setFixedWidth(60)
        btn.setStyleSheet(
            "background:#005599; color:#fff; border:none; padding:4px;"
            "border-radius:3px;"
        )
        btn.clicked.connect(self._on_connect)
        h.addWidget(btn)

        root.addWidget(bar)

        # 定时刷新 UDP 连通状态（每 2 秒）
        self._udp_ok_timer = QTimer(self)
        self._udp_ok_timer.setInterval(2000)
        self._udp_ok_timer.timeout.connect(self._refresh_udp_indicator)
        self._udp_ok_timer.start()

    @staticmethod
    def _dot_label(name: str) -> QLabel:
        lbl = QLabel(f"● {name}")
        lbl.setStyleSheet(_GRAY)
        lbl.setFont(QFont("Monospace", 9))
        return lbl

    # ------------------------------------------------------------------ RTSP
    def _start_rtsp(self):
        self.rtsp_player = FFmpegRTSPPlayer(RTSP_URL, FRAME_W, FRAME_H)
        self.rtsp_player.frame_updated.connect(self.video_widget.update_frame)
        self.rtsp_player.error_occurred.connect(self._on_video_error)
        self.rtsp_player.start()
        logger.info(f"RTSP player started: {RTSP_URL}")

    # ------------------------------------------------------------------ STM32
    def _start_stm32(self):
        self.stm32 = STM32Reader(port=STM32_PORT)
        self.stm32.frame_received.connect(self._on_stm32_frame)
        self.stm32.error_occurred.connect(self._on_stm32_error)
        self.stm32.start()

    def _on_stm32_frame(self, frame: ControlFrame):
        self._lbl_stm32.setStyleSheet(_GREEN)
        self.udp_sender.update(frame)
        # 更新 ESTOP / REMOTE 指示
        self._lbl_estop.setStyleSheet(_RED if frame.estop else _GRAY)
        self._lbl_remote.setStyleSheet(_GREEN if frame.remote_active else _GRAY)

    def _on_stm32_error(self, msg: str):
        self._lbl_stm32.setStyleSheet(_RED)
        logger.warning(f"STM32 error: {msg}")

    # ------------------------------------------------------------------ UDP
    def _start_udp_sender(self):
        self.udp_sender = UDPControlSender()
        self.udp_sender.send_error.connect(self._on_udp_error)
        self.udp_sender.start()
        self._udp_last_error = False

    def _on_udp_error(self, msg: str):
        self._udp_last_error = True
        self._lbl_udp.setStyleSheet(_RED)
        logger.warning(f"UDP send error: {msg}")

    def _refresh_udp_indicator(self):
        if not self._udp_last_error:
            self._lbl_udp.setStyleSheet(_GREEN)
        self._udp_last_error = False

    def _on_connect(self):
        ip = self._ip_edit.text().strip()
        if not ip:
            return
        self.udp_sender.set_target(ip)
        logger.info(f"UDP target set to {ip}")

    # ------------------------------------------------------------------ 事件
    def _on_video_error(self, msg: str):
        logger.error(f"video error: {msg}")
        QMessageBox.warning(self, "视频流错误", msg)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F11:
            self.showNormal() if self.isFullScreen() else self.showFullScreen()
        elif event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.showNormal()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        logger.info("closing, releasing resources...")

        # 断开信号
        try:
            self.rtsp_player.frame_updated.disconnect()
            self.rtsp_player.error_occurred.disconnect()
        except Exception:
            pass

        # 停止 RTSP（最多等 2 秒）
        self.rtsp_player.stop()
        if not self.rtsp_player.wait(2000):
            logger.warning("RTSP thread timeout, terminating")
            self.rtsp_player.terminate()
            self.rtsp_player.wait(500)

        # 停止 STM32 读取
        self.stm32.stop()
        self.stm32.wait(1000)

        # 停止 UDP 发送
        self.udp_sender.stop()
        self.udp_sender.wait(1000)

        # 释放 GPU 资源
        self.video_widget.cleanup()

        logger.info("all resources released")
        event.accept()


# ------------------------------------------------------------------ 入口
if __name__ == "__main__":
    # QSurfaceFormat 必须在 QApplication 之前设置
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    fmt.setSamples(4)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    fmt.setSwapInterval(1)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 10))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
