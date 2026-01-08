import sys
import logging
from PySide6.QtWidgets import QApplication, QWidget, QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QFont, QSurfaceFormat

# ✅ 导入编译后的UI类
from ui.window_ui import Ui_Camera
from gui.video_opengl_widget import VideoOpenGLWidget
from stream.ffmpeg_player import FFmpegRTSPPlayer

# 日志配置
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MainWindow")


# ---------------- 主窗口 ----------------
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        # ✅ 加载编译后的UI
        self.ui = Ui_Camera()
        self.ui.setupUi(self)

        # RTSP播放器线程
        self.rtsp_player = None

        # 初始化视频控件
        self._init_video_widget()

        # 启动RTSP视频流
        self._start_rtsp_playback()

        # 窗口设置
        self.resize(1280, 800)
        self.setWindowTitle("RTSP 视频监控终端 - OpenGL加速")

        logger.info("✅ 主窗口初始化完成")

    # ---------------- 视频控件初始化 ----------------
    def _init_video_widget(self):
        """初始化视频显示控件"""
        # ✅ 检查 video_widget 是否是 VideoOpenGLWidget 实例
        if isinstance(self.ui.video_widget, VideoOpenGLWidget):
            logger.info("✅ VideoOpenGLWidget 加载成功，使用OpenGL硬件渲染")
            self.video_widget = self.ui.video_widget
        else:
            logger.error("❌ video_widget 不是 VideoOpenGLWidget 类型")
            QMessageBox.critical(self, "错误", "视频控件类型错误，无法使用OpenGL渲染")
            sys.exit(1)

        # 设置视频控件属性
        logger.info(f"视频控件尺寸: {self.video_widget.width()}x{self.video_widget.height()}")

    # ---------------- RTSP视频流 ----------------
    def _start_rtsp_playback(self):
        """启动RTSP视频播放"""
        # RTSP视频流地址
        rtsp_url = "rtsp://192.168.1.36:554/ch01.264"

        # 获取视频控件尺寸
        width = self.video_widget.width() or 1280
        height = self.video_widget.height() or 720

        # 创建RTSP播放器
        self.rtsp_player = FFmpegRTSPPlayer(rtsp_url, width, height)

        # 连接信号
        self.rtsp_player.frame_updated.connect(self._update_video_frame)
        self.rtsp_player.error_occurred.connect(self._on_video_error)

        # 启动播放
        self.rtsp_player.start()

        logger.info(f"✅ RTSP视频流启动: {rtsp_url} ({width}x{height})")

    def _update_video_frame(self, q_image):
        """
        更新视频帧显示
        :param q_image: QImage对象
        """
        # ✅ 使用OpenGL渲染更新帧
        if hasattr(self.video_widget, 'update_frame'):
            self.video_widget.update_frame(q_image)
        else:
            # 降级方案：使用QLabel显示（如果video_widget不支持update_frame）
            logger.warning("VideoOpenGLWidget 不支持 update_frame 方法，使用降级方案")
            pix = QPixmap.fromImage(
                q_image.scaled(
                    self.video_widget.width(),
                    self.video_widget.height(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            )
            if hasattr(self.video_widget, 'setPixmap'):
                self.video_widget.setPixmap(pix)

    def _on_video_error(self, error_msg):
        """
        视频流错误处理
        :param error_msg: 错误信息
        """
        logger.error(f"❌ 视频流错误: {error_msg}")
        QMessageBox.warning(self, "视频流错误", f"视频流发生错误:\n{error_msg}")

    # ---------------- 键盘事件处理 ----------------
    def keyPressEvent(self, event):
        """键盘事件处理 - 支持ESC退出全屏，F11切换全屏"""
        if event.key() == Qt.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
                logger.info("退出全屏")
        elif event.key() == Qt.Key_F11:
            if self.isFullScreen():
                self.showNormal()
                logger.info("退出全屏")
            else:
                self.showFullScreen()
                logger.info("进入全屏")
        else:
            super().keyPressEvent(event)

    # ---------------- 资源清理 ----------------
    def closeEvent(self, event):
        """窗口关闭事件 - 清理资源"""
        logger.info("开始清理资源...")

        # ✅ 断开RTSP信号连接
        if self.rtsp_player:
            try:
                self.rtsp_player.frame_updated.disconnect()
                self.rtsp_player.error_occurred.disconnect()
                logger.info("✅ RTSP信号已断开")
            except Exception as e:
                logger.warning(f"断开RTSP信号失败: {e}")

        # ✅ 停止RTSP线程
        if self.rtsp_player and self.rtsp_player.isRunning():
            logger.info("正在停止RTSP播放器...")
            self.rtsp_player.stop()
            self.rtsp_player.wait(2000)  # 等待最多2秒

            if self.rtsp_player.isRunning():
                logger.warning("RTSP线程未能正常停止，强制终止")
                self.rtsp_player.terminate()
            else:
                logger.info("✅ RTSP播放器已停止")

        # ✅ 清理OpenGL资源
        if hasattr(self.video_widget, 'cleanup'):
            try:
                self.video_widget.cleanup()
                logger.info("✅ OpenGL资源已清理")
            except Exception as e:
                logger.error(f"清理OpenGL资源失败: {e}")

        # 释放引用
        self.rtsp_player = None

        logger.info("✅ 资源清理完成，窗口即将关闭")
        event.accept()


# ---------------- 程序入口 ----------------
if __name__ == "__main__":
    # ✅ OpenGL设置（必须在QApplication之前）
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)  # OpenGL 3.3
    fmt.setProfile(QSurfaceFormat.CoreProfile)  # 核心模式
    fmt.setSwapInterval(1)  # 垂直同步，防止撕裂
    fmt.setDepthBufferSize(24)  # 深度缓冲区
    fmt.setStencilBufferSize(8)  # 模板缓冲区
    fmt.setSamples(4)  # 4x抗锯齿
    QSurfaceFormat.setDefaultFormat(fmt)

    logger.info("✅ OpenGL配置完成")

    # 创建应用程序
    app = QApplication(sys.argv)

    # 设置应用程序字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    # 创建并显示主窗口
    window = MainWindow()
    window.show()

    logger.info("✅ 应用程序启动成功")

    # 进入事件循环
    sys.exit(app.exec())
