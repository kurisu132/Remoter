# -*- coding: utf-8 -*-
import sys
import logging
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QPushButton
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice, Qt
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtGui import QFont
import numpy as np
from OpenGL.GL import *

from api.digest_auth import digest_auth_request
from api.light_control import LightControlClient
from api.ptz_control import PTZControlClient
from stream.ffmpeg_player import FFmpegRTSPPlayer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MainWindow")


# ---------------- OpenGL 视频控件 ----------------
class VideoWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame = None
        self._texture_id = None

    def update_frame(self, frame: np.ndarray):
        self._frame = frame
        self.update()

    def initializeGL(self):
        glEnable(GL_TEXTURE_2D)
        self._texture_id = glGenTextures(1)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        if self._frame is None:
            return
        frame = np.flipud(self._frame)
        h, w, _ = frame.shape
        glBindTexture(GL_TEXTURE_2D, self._texture_id)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, w, h, 0, GL_RGB, GL_UNSIGNED_BYTE, frame)
        glBegin(GL_QUADS)
        glTexCoord2f(0,0); glVertex2f(-1,-1)
        glTexCoord2f(1,0); glVertex2f(1,-1)
        glTexCoord2f(1,1); glVertex2f(1,1)
        glTexCoord2f(0,1); glVertex2f(-1,1)
        glEnd()
        glBindTexture(GL_TEXTURE_2D,0)

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(-1,1,-1,1,-1,1)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()


# ---------------- MainWindow ----------------
class MainWindow(QMainWindow):
    def __init__(self, ui_file_path="../ui/window.ui"):
        super().__init__()
        self.ui = self._load_ui(ui_file_path)
        self.rtsp_player = None

        # 替换 video 控件为 OpenGLWidget
        video_placeholder = self.ui.findChild(QOpenGLWidget, "video")
        self.video_container = VideoWidget(parent=video_placeholder.parent())
        layout = video_placeholder.parent().layout()
        if layout:
            layout.addWidget(self.video_container)

        # 灯控按钮
        self.btn_open = self.ui.findChild(QPushButton, "open")
        self.btn_close = self.ui.findChild(QPushButton, "close")
        self.btn_open.clicked.connect(self._handle_light_on)
        self.btn_close.clicked.connect(self._handle_light_off)

        # 云台按钮
        self.ptz_client = PTZControlClient(host="192.168.0.36", username="admin", password="123456")
        self._init_ptz_buttons()

        # 认证按钮
        self.autho_button = self.ui.findChild(QPushButton, "autho")
        self.autho_button.clicked.connect(self._handle_autho_click)

        self._start_rtsp_playback()
        self.show()

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

    def _start_rtsp_playback(self):
        rtsp_url = "rtsp://192.168.0.36:554/ch01.264"
        self.rtsp_player = FFmpegRTSPPlayer(rtsp_url, width=1280, height=720)
        self.rtsp_player.frame_ready.connect(self.video_container.update_frame)
        self.rtsp_player.error_occurred.connect(lambda e: QMessageBox.warning(self, "视频流错误", e))
        self.rtsp_player.start()
        logger.info(f"RTSP 播放启动: {rtsp_url}")

    # ---------------- 灯控 ----------------
    def _handle_light_on(self):
        client = LightControlClient(host="192.168.0.36", username="admin", password="123456")
        client.turn_light_on("Warm", 100)

    def _handle_light_off(self):
        client = LightControlClient(host="192.168.0.36", username="admin", password="123456")
        client.turn_light_off()

    # ---------------- 云台控制 ----------------
    def _init_ptz_buttons(self):
        self.ptz_buttons = {}
        for name in ["up","down","left","right"]:
            btn = self.ui.findChild(QPushButton, name)
            if btn:
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

    # ---------------- 认证 ----------------
    def _handle_autho_click(self):
        from api.digest_auth import digest_auth_request
        try:
            success, _ = digest_auth_request({
                "url":"http://192.168.0.36:80/digest/frmUserLogin",
                "username":"admin","password":"123456",
                "http_method":"POST","request_data":{"Type":0,"Ch":0,"Data":{}},
                "headers":{"Content-Type":"application/json; charset=utf-8"},
                "timeout":10
            })
            QMessageBox.information(self,"认证结果","认证成功" if success else "认证失败")
        except Exception as e:
            QMessageBox.critical(self,"认证失败",str(e))

    def closeEvent(self, event):
        if self.rtsp_player and self.rtsp_player.isRunning():
            self.rtsp_player.stop()
        event.accept()


# ---------------- 程序入口 ----------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 10))
    window = MainWindow(ui_file_path="../ui/window.ui")
    sys.exit(app.exec())
