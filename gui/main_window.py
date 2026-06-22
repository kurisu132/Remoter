"""
MainWindow — Phase 1 控制框架（业务逻辑）

UI 布局由 ui/window_ui.py 提供，本文件只包含：
  - RTSP 拉流管理
  - STM32 串口读取
  - UDP 控制发送
  - PTZ / 补光灯 API 调用
  - 状态指示灯更新
  - 窗口生命周期
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
import queue
import signal
import threading

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QSurfaceFormat
from PySide6.QtWidgets import QApplication, QWidget

from api.light_control import LightControlClient
from api.ptz_control import PTZControlClient
from stream.ffmpeg_player import FFmpegRTSPPlayer
from stream.stm32_reader import ControlFrame, STM32Reader
from stream.udp_control_sender import UDPControlSender, load_config
from ui.window_ui import WindowUI, GREEN, RED, GRAY, YELLOW

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MainWindow")

RTSP_URL  = "rtsp://192.168.1.36:554/ch01.264"
TEST_URL  = "test://offline"
FRAME_W   = 2592
FRAME_H   = 1904


class MainWindow(QWidget):
    def __init__(self, test_mode: bool = False):
        super().__init__()
        self._test_mode = test_mode

        WindowUI.setup_ui(self)          # 构建全部 UI
        self._start_rtsp()
        self._start_udp_sender()
        self._start_stm32()
        self._start_camera_clients()

        self.resize(1280, 800)
        title = "VLink 监控终端" + (" [离线测试源]" if test_mode else "")
        self.setWindowTitle(title)
        logger.info("MainWindow initialized" + (" [test mode]" if test_mode else ""))

    # ──────────────────────────────────────────────────────────────── RTSP
    def _start_rtsp(self):
        url = TEST_URL if self._test_mode else load_config().get("rtsp_url", RTSP_URL)
        self.rtsp_player = FFmpegRTSPPlayer(url, FRAME_W, FRAME_H)
        self.rtsp_player.frame_updated.connect(self.video_widget.update_frame)
        self.rtsp_player.error_occurred.connect(self._on_video_error)
        self.rtsp_player.status_changed.connect(self._on_rtsp_status)
        self.rtsp_player.start()
        logger.info(f"RTSP player started: {url}")

    def _on_rtsp_status(self, status: str):
        prefix = " background-color: transparent;"
        if status == "streaming":
            self._lbl_rtsp.setStyleSheet(GREEN + prefix)
            self._lbl_rtsp.setText("● 视频在线")
        elif status in ("connecting",) or status.startswith("reconnecting"):
            self._lbl_rtsp.setStyleSheet(YELLOW + prefix)
            self._lbl_rtsp.setText("● 连接中")
        else:  # stopped
            self._lbl_rtsp.setStyleSheet(GRAY + prefix)
            self._lbl_rtsp.setText("● RTSP")

    def _on_video_error(self, msg: str):
        logger.error(f"video error: {msg}")
        self._lbl_rtsp.setStyleSheet(RED + " background-color: transparent;")
        self._lbl_rtsp.setText("● RTSP 错误")

    # ─────────────────────────────────────────────────────────────── STM32
    def _start_stm32(self):
        port = load_config().get("stm32_port", "/dev/ttyACM0")
        self.stm32 = STM32Reader(port=port)
        self.stm32.frame_received.connect(self._on_stm32_frame)
        self.stm32.error_occurred.connect(self._on_stm32_error)
        self.stm32.start()

    def _on_stm32_frame(self, frame: ControlFrame):
        prefix = " background-color: transparent;"
        self._lbl_stm32.setStyleSheet(GREEN + prefix)
        self.udp_sender.update(frame)
        self._lbl_estop.setStyleSheet((RED if frame.estop else GRAY) + prefix)
        self._lbl_remote.setStyleSheet((GREEN if frame.remote_active else GRAY) + prefix)

    def _on_stm32_error(self, msg: str):
        self._lbl_stm32.setStyleSheet(RED + " background-color: transparent;")
        logger.warning(f"STM32 error: {msg}")

    # ──────────────────────────────────────────────────────────────── UDP
    def _start_udp_sender(self):
        self.udp_sender = UDPControlSender()
        self.udp_sender.send_error.connect(self._on_udp_error)
        self.udp_sender.start()
        self._udp_last_error = False

    def _on_udp_error(self, msg: str):
        self._udp_last_error = True
        self._lbl_udp.setStyleSheet(RED + " background-color: transparent;")
        logger.warning(f"UDP send error: {msg}")

    def _refresh_udp_indicator(self):
        if not self._udp_last_error:
            self._lbl_udp.setStyleSheet(GREEN + " background-color: transparent;")
        self._udp_last_error = False

    def _on_connect(self):
        ip = self._ip_edit.text().strip()
        if ip:
            self.udp_sender.set_target(ip)
            logger.info(f"UDP target set to {ip}")

    # ─────────────────────────────────────────────── 摄像头 API 客户端
    def _start_camera_clients(self):
        cfg = load_config()
        host = cfg.get("camera_host", "192.168.1.36")
        user = cfg.get("camera_user", "admin")
        pwd  = cfg.get("camera_pass", "123456")
        self._ptz   = PTZControlClient(host=host, username=user, password=pwd)
        self._light = LightControlClient(host=host, username=user, password=pwd)
        self._ptz_queue = queue.Queue()
        threading.Thread(target=self._ptz_worker_loop, daemon=True).start()
        logger.info(f"camera API clients ready: {host}")

    def _run_in_thread(self, fn, *args, **kwargs):
        threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True).start()

    # ── PTZ ──
    def _ptz_worker_loop(self):
        while True:
            fn = self._ptz_queue.get()
            if fn is None:
                break
            try:
                fn()
            except Exception as e:
                logger.warning(f"PTZ command error: {e}")

    def _ptz_move(self, direction: str):
        cmd_map = {"up": self._ptz.pan_up, "down": self._ptz.pan_down,
                   "left": self._ptz.pan_left, "right": self._ptz.pan_right}
        fn = cmd_map.get(direction)
        if fn:
            self._ptz_queue.put(fn)

    def _ptz_stop(self):
        self._ptz_queue.put(self._ptz.stop)

    # ── 补光灯 ──
    def _on_light_on(self):
        self._run_in_thread(self._light.turn_light_on)

    def _on_light_off(self):
        self._run_in_thread(self._light.turn_light_off)

    # ──────────────────────────────────────────────────────────────── 事件
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

        self._ptz_queue.put(None)

        self.stm32.stop()
        self.stm32.wait(1000)

        self.udp_sender.stop()
        self.udp_sender.wait(1000)

        self.video_widget.cleanup()

        logger.info("all resources released")
        event.accept()


# ────────────────────────────────────────────────────────────────── 入口
def _run(test_mode: bool = False):
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setSamples(4)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    fmt.setSwapInterval(1)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei", 10))

    signal.signal(signal.SIGINT, lambda *_: app.quit())
    # 定期唤醒 Python 信号队列，否则 Qt 事件循环会阻断 SIGINT
    _sig_timer = QTimer()
    _sig_timer.start(200)
    _sig_timer.timeout.connect(lambda: None)

    window = MainWindow(test_mode=test_mode)
    window.show()

    sys.exit(app.exec())


def main():
    _run(test_mode=False)


def main_test():
    _run(test_mode=True)


if __name__ == "__main__":
    _run(test_mode="--test" in sys.argv)
