import sys
import logging
from PySide6.QtWidgets import QApplication, QWidget, QMessageBox, QPushButton
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap, QFont, QSurfaceFormat

# ✅ 导入编译后的UI类
from ui.window_ui import Ui_Camera
from gui.video_opengl_widget import VideoOpenGLWidget

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
                host=self.host, username=self.username,
                password=self.password, opaque=self.opaque
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
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        # ✅ 加载编译后的UI
        self.ui = Ui_Camera()
        self.ui.setupUi(self)

        # 线程对象
        self.rtsp_player = None
        self.auth_thread = None
        self.light_thread = None

        # PTZ云台客户端
        self.ptz_client = PTZControlClient(
            host="192.168.1.36", username="admin", password="123456"
        )

        # 补光灯配置
        self.light_config = {
            "host": "192.168.1.36",
            "username": "admin",
            "password": "123456",
            "opaque": "5ccc069c403ebaf9f0171e9517f40e41"
        }

        # 初始化
        self._init_ui_elements()
        self._init_control_buttons()
        self._start_rtsp_playback()

        # 窗口设置
        self.resize(1280, 800)
        self.setWindowTitle("RTSP 视频监控终端 - OpenGL加速")

    # ---------------- UI初始化 ----------------
    def _init_ui_elements(self):
        """初始化UI控件"""
        # ✅ video_widget 已经是 VideoOpenGLWidget 实例
        if isinstance(self.ui.video_widget, VideoOpenGLWidget):
            logger.info("✅ VideoOpenGLWidget 加载成功，使用OpenGL硬件渲染")
            self.video_widget = self.ui.video_widget
        else:
            logger.error("❌ video_widget 不是 VideoOpenGLWidget 类型")
            QMessageBox.critical(self, "错误", "视频控件类型错误")
            sys.exit(1)

        # 兼容性别名
        self.video_label = self.video_widget

        logger.info("✅ UI控件初始化完成")

    def _init_control_buttons(self):
        """初始化所有控制按钮"""
        # 认证按钮
        self.ui.autho.setText("点击认证")
        self.ui.autho.clicked.connect(self._handle_autho_click)

        # 补光灯按钮
        self.ui.open.setText("开灯")
        self.ui.close.setText("关灯")
        self.ui.open.clicked.connect(self._handle_light_on)
        self.ui.close.clicked.connect(self._handle_light_off)

        # 云台控制按钮
        self.ui.up.pressed.connect(lambda: self._ptz_move("up", is_stop=0))
        self.ui.up.released.connect(lambda: self._ptz_move("up", is_stop=1))

        self.ui.down.pressed.connect(lambda: self._ptz_move("down", is_stop=0))
        self.ui.down.released.connect(lambda: self._ptz_move("down", is_stop=1))

        self.ui.left.pressed.connect(lambda: self._ptz_move("left", is_stop=0))
        self.ui.left.released.connect(lambda: self._ptz_move("left", is_stop=1))

        self.ui.right.pressed.connect(lambda: self._ptz_move("right", is_stop=0))
        self.ui.right.released.connect(lambda: self._ptz_move("right", is_stop=1))

        # 全屏按钮
        self.ui.fullscreen.clicked.connect(self._handle_fullscreen)

        logger.info("✅ 所有按钮信号已连接")

    # ---------------- 云台控制 ----------------
    def _ptz_move(self, direction, is_stop=0):
        """云台移动控制"""
        cmd_map = {"up": 21, "down": 22, "left": 23, "right": 24}
        cmd = cmd_map.get(direction)
        if cmd:
            try:
                self.ptz_client.ptz_control(cmd=cmd, is_stop=is_stop)
                logger.debug(f"云台控制: {direction} {'停止' if is_stop else '移动'}")
            except Exception as e:
                logger.exception(f"云台控制失败 {direction} {is_stop}")

    # ---------------- RTSP视频流 ----------------
    def _start_rtsp_playback(self):
        """启动RTSP视频播放"""
        rtsp_url = "rtsp://192.168.1.36:554/ch01.264"
        width = self.video_widget.width() or 1280
        height = self.video_widget.height() or 720

        self.rtsp_player = FFmpegRTSPPlayer(rtsp_url, width, height)
        self.rtsp_player.frame_updated.connect(self._update_video_frame)
        self.rtsp_player.error_occurred.connect(
            lambda err: QMessageBox.warning(self, "视频流错误", err)
        )
        self.rtsp_player.start()

        logger.info(f"✅ RTSP视频流启动: {rtsp_url}")

    def _update_video_frame(self, q_image):
        """更新视频帧显示"""
        if hasattr(self.video_widget, 'update_frame'):
            # OpenGL渲染
            self.video_widget.update_frame(q_image)
        else:
            # QLabel降级方案
            pix = QPixmap.fromImage(
                q_image.scaled(
                    self.video_widget.width(),
                    self.video_widget.height(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            )
            self.video_widget.setPixmap(pix)

    # ---------------- 认证处理 ----------------
    def _handle_autho_click(self):
        """处理认证按钮点击"""
        if self.auth_thread and self.auth_thread.isRunning():
            QMessageBox.information(self, "提示", "认证进行中，请稍候...")
            return

        self.ui.autho.setEnabled(False)
        self.ui.autho.setText("认证中...")
        QApplication.processEvents()

        auth_config = {
            "url": "http://192.168.1.36:80/digest/frmUserLogin",
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

        logger.info("认证子线程已启动")

    def _on_auth_finished(self, success, msg):
        """认证完成回调"""
        self.ui.autho.setEnabled(True)
        self.ui.autho.setText("已认证" if success else "点击认证")

        if success:
            QMessageBox.information(self, "认证成功", msg)
        else:
            QMessageBox.critical(self, "认证失败", msg)

        self.auth_thread = None

    # ---------------- 补光灯控制 ----------------
    def _handle_light_on(self):
        """开灯"""
        if self.light_thread and self.light_thread.isRunning():
            QMessageBox.information(self, "提示", "开灯操作进行中，请稍候...")
            return

        self.ui.open.setEnabled(False)
        self.ui.open.setText("开启中...")
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
        """关灯"""
        if self.light_thread and self.light_thread.isRunning():
            QMessageBox.information(self, "提示", "灯控操作进行中，请稍候...")
            return

        self.ui.close.setEnabled(False)
        self.ui.close.setText("关闭中...")
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
        """灯控操作完成回调"""
        self.ui.open.setEnabled(True)
        self.ui.open.setText("开灯")
        self.ui.close.setEnabled(True)
        self.ui.close.setText("关灯")

        if success:
            QMessageBox.information(self, "成功", msg)
        else:
            QMessageBox.critical(self, "失败", msg)

        self.light_thread = None

    # ---------------- 全屏控制 ----------------
    def _handle_fullscreen(self):
        """全屏切换"""
        if self.isFullScreen():
            self.showNormal()
            logger.info("退出全屏")
        else:
            self.showFullScreen()
            logger.info("进入全屏")

    # ---------------- 资源清理 ----------------
    def closeEvent(self, event):
        """窗口关闭事件"""
        logger.info("开始清理资源...")

        # 断开RTSP信号
        if self.rtsp_player:
            try:
                self.rtsp_player.frame_updated.disconnect()
                self.rtsp_player.error_occurred.disconnect()
            except Exception:
                pass

        # 停止RTSP线程
        if self.rtsp_player and self.rtsp_player.isRunning():
            self.rtsp_player.stop()
            self.rtsp_player.wait(1000)

        # 停止认证线程
        if self.auth_thread and self.auth_thread.isRunning():
            self.auth_thread.quit()
            self.auth_thread.wait(500)

        # 停止灯控线程
        if self.light_thread and self.light_thread.isRunning():
            self.light_thread.quit()
            self.light_thread.wait(500)

        # ✅ 清理OpenGL资源
        if hasattr(self.video_widget, 'cleanup'):
            try:
                self.video_widget.cleanup()
                logger.info("✅ OpenGL资源已清理")
            except Exception as e:
                logger.error(f"清理OpenGL资源失败: {e}")

        # 释放引用
        self.rtsp_player = None
        self.auth_thread = None
        self.light_thread = None

        logger.info("✅ 资源清理完成")
        event.accept()


# ---------------- 程序入口 ----------------
if __name__ == "__main__":
    # ✅ OpenGL设置（必须在QApplication之前）
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    fmt.setSwapInterval(1)  # 垂直同步
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)

    # 设置字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    # 创建主窗口
    window = MainWindow()
    window.show()

    logger.info("✅ 应用程序启动成功")

    sys.exit(app.exec())