import sys
import logging
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QLabel, QPushButton
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, Qt, QThread, Signal
from PySide6.QtGui import QPixmap, QFont

from api.digest_auth import digest_auth_request
from api.light_control import LightControlClient
from api.ptz_control import PTZControlClient
from stream.ffmpeg_player import FFmpegRTSPPlayer

# 日志配置
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MainWindow")


# ---------------- Digest认证子线程 ----------------
class AuthWorker(QThread):
    finished = Signal(bool, str)  # (是否成功, 返回消息)
    def __init__(self, auth_config):
        super().__init__()
        self.auth_config = auth_config
    def run(self):
        try:
            success, result = digest_auth_request(self.auth_config)
            if success:
                self.finished.emit(True, "认证成功")
            else:
                self.finished.emit(False, str(result))
        except Exception as e:
            logger.exception("AuthWorker 异常")
            self.finished.emit(False, str(e))


# ---------------- 补光灯控制子线程 ----------------
class LightWorker(QThread):
    finished = Signal(bool, str)
    def __init__(self, host, username, password, opaque, action='on', params=None):
        super().__init__()
        self.host = host
        self.username = username
        self.password = password
        self.opaque = opaque
        self.action = action
        self.params = params or {}
    def run(self):
        try:
            client = LightControlClient(
                host=self.host, username=self.username, password=self.password, opaque=self.opaque
            )
            if self.action == 'on':
                mode = self.params.get('mode', 'Warm')
                brightness = self.params.get('brightness', 100)
                success, msg = client.turn_light_on(mode, brightness)
                self.finished.emit(success, msg if success else f"开灯失败：{msg}")
            elif self.action == 'off':
                success, msg = client.turn_light_off()
                self.finished.emit(success, msg if success else f"关灯失败：{msg}")
            else:
                self.finished.emit(False, f"未知操作：{self.action}")
        except Exception as e:
            logger.exception("LightWorker 异常")
            self.finished.emit(False, str(e))


# ---------------- 主窗口 ----------------
class MainWindow(QMainWindow):
    def __init__(self, ui_file_path="../ui/window.ui"):
        super().__init__()
        self.ui = self._load_ui(ui_file_path)

        self.rtsp_player = None
        self.auth_thread = None
        self.light_thread = None

        # PTZ云台客户端
        self.ptz_client = PTZControlClient(
            host="192.168.0.36", username="admin", password="123456"
        )

        self.light_config = {
            "host": "192.168.0.36",
            "username": "admin",
            "password": "123456",
            "opaque": "5ccc069c403ebaf9f0171e9517f40e41"
        }

        self._init_ui_elements()
        self._init_light_control_ui()
        self._init_ptz_control_ui()
        self._start_rtsp_playback()
        self.show()

    # ---------------- UI加载 ----------------
    def _load_ui(self, ui_file_path):
        ui_file = QFile(ui_file_path)
        if not ui_file.open(QIODevice.ReadOnly):
            QMessageBox.critical(None, "UI加载失败", f"无法打开 {ui_file_path}")
            sys.exit(1)
        loader = QUiLoader()
        ui = loader.load(ui_file, self)
        ui_file.close()
        if not ui:
            QMessageBox.critical(None, "UI错误", "UI文件加载失败")
            sys.exit(1)
        return ui

    # ---------------- 控件初始化 ----------------
    def _init_ui_elements(self):
        self.video_label = self.ui.findChild(QLabel, "video_label")
        if not self.video_label:
            QMessageBox.critical(self, "控件缺失", "未找到 video_label")
            sys.exit(1)
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setText("视频加载中...")

        self.autho_button = self.ui.findChild(QPushButton, "autho")
        if not self.autho_button:
            QMessageBox.critical(self, "控件缺失", "未找到认证按钮 autho")
            sys.exit(1)
        self.autho_button.setText("点击认证")
        self.autho_button.clicked.connect(self._handle_autho_click)

        self.setCentralWidget(self.ui)
        self.resize(1280, 800)
        self.setWindowTitle("RTSP 视频监控终端")

    # ---------------- 灯控 ----------------
    def _init_light_control_ui(self):
        self.btn_open = self.ui.findChild(QPushButton, "open")
        self.btn_close = self.ui.findChild(QPushButton, "close")
        if not self.btn_open or not self.btn_close:
            QMessageBox.critical(self, "控件缺失", "请确认 UI 中存在 open/close 按钮！")
            sys.exit(1)
        self.btn_open.setText("开灯")
        self.btn_close.setText("关灯")
        self.btn_open.clicked.connect(self._handle_light_on)
        self.btn_close.clicked.connect(self._handle_light_off)

    # ---------------- 云台控制 ----------------
    def _init_ptz_control_ui(self):
        # 云台上下左右按键
        self.ptz_buttons = {}
        for name in ["up", "down", "left", "right"]:
            btn = self.ui.findChild(QPushButton, name)
            if not btn:
                QMessageBox.critical(self, "控件缺失", f"未找到云台按钮 {name}")
                sys.exit(1)
            btn.pressed.connect(lambda n=name: self._ptz_move(n, is_stop=0))
            btn.released.connect(lambda n=name: self._ptz_move(n, is_stop=1))
            self.ptz_buttons[name] = btn

    def _ptz_move(self, direction, is_stop=0):
        cmd_map = {"up":21, "down":22, "left":23, "right":24}
        cmd = cmd_map.get(direction)
        if cmd:
            try:
                self.ptz_client.ptz_control(cmd=cmd, is_stop=is_stop)
            except Exception as e:
                logger.exception(f"云台控制失败 {direction} {is_stop}")

    # ---------------- RTSP ----------------
    def _start_rtsp_playback(self):
        rtsp_url = "rtsp://192.168.0.36:554/ch01.264"
        width = self.video_label.width() or 1280
        height = self.video_label.height() or 720
        self.rtsp_player = FFmpegRTSPPlayer(rtsp_url, width, height)
        self.rtsp_player.frame_updated.connect(self._update_video_frame)
        self.rtsp_player.error_occurred.connect(lambda err: QMessageBox.warning(self, "视频流错误", err))
        self.rtsp_player.start()
        logger.info(f"RTSP启动: {rtsp_url}")

    def _update_video_frame(self, q_image):
        pix = QPixmap.fromImage(
            q_image.scaled(
                self.video_label.width(),
                self.video_label.height(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
        )
        self.video_label.setPixmap(pix)
        self.video_label.setText("")

    # ---------------- 认证 ----------------
    def _handle_autho_click(self):
        if self.auth_thread and self.auth_thread.isRunning():
            QMessageBox.information(self, "提示", "认证进行中，请稍候...")
            return
        self.autho_button.setEnabled(False)
        self.autho_button.setText("认证中...")
        QApplication.processEvents()
        auth_config = {
            "url": "http://192.168.0.36:80/digest/frmUserLogin",
            "username": "admin",
            "password": "123456",
            "http_method": "POST",
            "request_data": {"Type": 0, "Ch": 0, "Data": {}},
            "headers": {"Content-Type": "application/json; charset=utf-8"},
            "timeout": 10
        }
        self.auth_thread = AuthWorker(auth_config)
        self.auth_thread.finished.connect(self._on_auth_finished)
        self.auth_thread.start()
        logger.info("[MainWindow] 已启动认证子线程")

    def _on_auth_finished(self, success, msg):
        self.autho_button.setEnabled(True)
        self.autho_button.setText("已认证" if success else "点击认证")
        if success:
            QMessageBox.information(self, "认证成功", msg)
        else:
            QMessageBox.critical(self, "认证失败", msg)
        self.auth_thread = None

    # ---------------- 灯控操作 ----------------
    def _handle_light_on(self):
        if self.light_thread and self.light_thread.isRunning():
            QMessageBox.information(self, "提示", "开灯操作进行中，请稍候...")
            return
        self.btn_open.setEnabled(False)
        self.btn_open.setText("开启中...")
        QApplication.processEvents()
        self.light_thread = LightWorker(
            host=self.light_config["host"],
            username=self.light_config["username"],
            password=self.light_config["password"],
            opaque=self.light_config["opaque"],
            action='on',
            params={'mode': 'Warm', 'brightness': 100}
        )
        self.light_thread.finished.connect(self._on_light_finished)
        self.light_thread.start()

    def _handle_light_off(self):
        if self.light_thread and self.light_thread.isRunning():
            QMessageBox.information(self, "提示", "灯控操作进行中，请稍候...")
            return
        self.btn_close.setEnabled(False)
        self.btn_close.setText("关闭中...")
        QApplication.processEvents()
        self.light_thread = LightWorker(
            host=self.light_config["host"],
            username=self.light_config["username"],
            password=self.light_config["password"],
            opaque=self.light_config["opaque"],
            action='off'
        )
        self.light_thread.finished.connect(self._on_light_finished)
        self.light_thread.start()

    def _on_light_finished(self, success, msg):
        self.btn_open.setEnabled(True)
        self.btn_open.setText("开灯")
        self.btn_close.setEnabled(True)
        self.btn_close.setText("关灯")
        if success:
            QMessageBox.information(self, "成功", msg)
        else:
            QMessageBox.critical(self, "失败", msg)
        self.light_thread = None

    # ---------------- 安全关闭 ----------------
    def closeEvent(self, event):
        if self.rtsp_player:
            try: self.rtsp_player.frame_updated.disconnect()
            except Exception: pass
            try: self.rtsp_player.error_occurred.disconnect()
            except Exception: pass

        if self.rtsp_player and self.rtsp_player.isRunning():
            self.rtsp_player.stop()
            self.rtsp_player.wait(1000)

        if self.auth_thread and self.auth_thread.isRunning():
            self.auth_thread.quit()
            self.auth_thread.wait(500)

        if self.light_thread and self.light_thread.isRunning():
            self.light_thread.quit()
            self.light_thread.wait(500)

        self.rtsp_player = None
        self.auth_thread = None
        self.light_thread = None

        event.accept()


# ---------------- 程序入口 ----------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)
    window = MainWindow(ui_file_path="../ui/window.ui")
    sys.exit(app.exec())
