"""
MainWindow — Phase 1 控制框架

布局：
  ┌──────────────────────────────────┬────────────┐
  │        VideoOpenGLWidget         │  右侧面板  │
  │                                  │  补光灯    │
  │                                  │  云台方向  │
  ├──────────────────────────────────┴────────────┤
  │ STM32:● UDP:● ESTOP:○ REMOTE:○  IP:[___] [连接] │
  └───────────────────────────────────────────────┘
"""
import logging
import sys
import threading

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QSurfaceFormat
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from api.light_control import LightControlClient
from api.ptz_control import PTZControlClient
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

_GREEN = "color: #00cc44; font-size: 16px;"
_RED   = "color: #ff3333; font-size: 16px;"
_GRAY  = "color: #888888; font-size: 16px;"

_BTN_STYLE = (
    "QPushButton { background:#2a2a2a; color:#ffffff; border:1px solid #555;"
    " border-radius:4px; padding:4px; font-size:14px; }"
    " QPushButton:pressed { background:#005599; }"
    " QPushButton:disabled { color:#555555; }"
)
_BTN_LIGHT_ON  = "background:#cc8800; color:#fff; border:none; border-radius:4px; padding:6px;"
_BTN_LIGHT_OFF = "background:#444444; color:#fff; border:none; border-radius:4px; padding:6px;"


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()
        self._start_rtsp()
        self._start_udp_sender()
        self._start_stm32()
        self._start_camera_clients()
        self.resize(1280, 800)
        self.setWindowTitle("VLink 监控终端")
        logger.info("MainWindow initialized")

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 内容区（视频 + 右侧面板）──
        content = QWidget()
        ch = QHBoxLayout(content)
        ch.setContentsMargins(0, 0, 0, 0)
        ch.setSpacing(0)

        self.video_widget = VideoOpenGLWidget()
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        ch.addWidget(self.video_widget, stretch=1)
        ch.addWidget(self._build_right_panel())

        root.addWidget(content)

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
            "background:#005599; color:#fff; border:none; padding:4px; border-radius:3px;"
        )
        btn.clicked.connect(self._on_connect)
        h.addWidget(btn)

        root.addWidget(bar)

        self._udp_ok_timer = QTimer(self)
        self._udp_ok_timer.setInterval(2000)
        self._udp_ok_timer.timeout.connect(self._refresh_udp_indicator)
        self._udp_ok_timer.start()

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(180)
        panel.setStyleSheet("background: #111111;")
        v = QVBoxLayout(panel)
        v.setContentsMargins(8, 12, 8, 12)
        v.setSpacing(14)

        # ── 补光灯 ──
        lbl_light = QLabel("补光灯")
        lbl_light.setStyleSheet("color:#aaaaaa; font-size:12px;")
        lbl_light.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(lbl_light)

        light_row = QHBoxLayout()
        light_row.setSpacing(6)
        self._btn_light_on  = QPushButton("开")
        self._btn_light_off = QPushButton("关")
        self._btn_light_on.setStyleSheet(_BTN_LIGHT_ON)
        self._btn_light_off.setStyleSheet(_BTN_LIGHT_OFF)
        self._btn_light_on.clicked.connect(self._on_light_on)
        self._btn_light_off.clicked.connect(self._on_light_off)
        light_row.addWidget(self._btn_light_on)
        light_row.addWidget(self._btn_light_off)
        v.addLayout(light_row)

        # ── 云台 ──
        lbl_ptz = QLabel("云台")
        lbl_ptz.setStyleSheet("color:#aaaaaa; font-size:12px;")
        lbl_ptz.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(lbl_ptz)

        grid = QGridLayout()
        grid.setSpacing(4)
        self._btn_up    = QPushButton("↑")
        self._btn_down  = QPushButton("↓")
        self._btn_left  = QPushButton("←")
        self._btn_right = QPushButton("→")
        self._btn_stop  = QPushButton("■")
        for b in (self._btn_up, self._btn_down, self._btn_left,
                  self._btn_right, self._btn_stop):
            b.setStyleSheet(_BTN_STYLE)
            b.setFixedHeight(40)

        grid.addWidget(self._btn_up,    0, 1)
        grid.addWidget(self._btn_left,  1, 0)
        grid.addWidget(self._btn_stop,  1, 1)
        grid.addWidget(self._btn_right, 1, 2)
        grid.addWidget(self._btn_down,  2, 1)
        v.addLayout(grid)

        # 方向键按下/松开发送 PTZ 指令
        self._btn_up.pressed.connect(lambda: self._ptz_move("up"))
        self._btn_up.released.connect(self._ptz_stop)
        self._btn_down.pressed.connect(lambda: self._ptz_move("down"))
        self._btn_down.released.connect(self._ptz_stop)
        self._btn_left.pressed.connect(lambda: self._ptz_move("left"))
        self._btn_left.released.connect(self._ptz_stop)
        self._btn_right.pressed.connect(lambda: self._ptz_move("right"))
        self._btn_right.released.connect(self._ptz_stop)
        self._btn_stop.clicked.connect(self._ptz_stop)

        v.addStretch()
        return panel

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
        if ip:
            self.udp_sender.set_target(ip)
            logger.info(f"UDP target set to {ip}")

    # ------------------------------------------------------------------ 摄像头 API 客户端
    def _start_camera_clients(self):
        cfg = load_config()
        host = cfg.get("camera_host", "192.168.1.36")
        user = cfg.get("camera_user", "admin")
        pwd  = cfg.get("camera_pass", "123456")
        self._ptz   = PTZControlClient(host=host, username=user, password=pwd)
        self._light = LightControlClient(host=host, username=user, password=pwd)
        logger.info(f"camera API clients ready: {host}")

    def _run_in_thread(self, fn, *args, **kwargs):
        """在守护线程中执行阻塞的 HTTP 调用"""
        threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True).start()

    # ── PTZ ──
    def _ptz_move(self, direction: str):
        cmd_map = {"up": self._ptz.pan_up, "down": self._ptz.pan_down,
                   "left": self._ptz.pan_left, "right": self._ptz.pan_right}
        fn = cmd_map.get(direction)
        if fn:
            self._run_in_thread(fn)

    def _ptz_stop(self):
        self._run_in_thread(self._ptz.stop)

    # ── 补光灯 ──
    def _on_light_on(self):
        self._run_in_thread(self._light.turn_light_on)

    def _on_light_off(self):
        self._run_in_thread(self._light.turn_light_off)

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

        try:
            self.rtsp_player.frame_updated.disconnect()
            self.rtsp_player.error_occurred.disconnect()
        except Exception:
            pass

        self.rtsp_player.stop()
        if not self.rtsp_player.wait(2000):
            logger.warning("RTSP thread timeout, terminating")
            self.rtsp_player.terminate()
            self.rtsp_player.wait(500)

        self.stm32.stop()
        self.stm32.wait(1000)

        self.udp_sender.stop()
        self.udp_sender.wait(1000)

        self.video_widget.cleanup()

        logger.info("all resources released")
        event.accept()


# ------------------------------------------------------------------ 入口
if __name__ == "__main__":
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
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
