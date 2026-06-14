"""
OpenGL + FFmpeg 集成冒烟测试
使用生产用 VideoOpenGLWidget，验证端到端渲染路径在当前硬件上是否可用。
运行方式：python check.py
"""
import sys
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from PySide6.QtGui import QSurfaceFormat

from gui.video_opengl_widget import VideoOpenGLWidget
from stream.ffmpeg_player import FFmpegRTSPPlayer

RTSP_URL = "rtsp://192.168.1.36:554/ch01.264"
WIDTH, HEIGHT = 2592, 1904

if __name__ == "__main__":
    # QSurfaceFormat 必须在 QApplication 之前设置
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    fmt.setSamples(4)
    fmt.setDepthBufferSize(24)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)

    window = QWidget()
    window.setWindowTitle("OpenGL + FFmpeg 集成冒烟测试")
    window.resize(1280, 720)

    layout = QVBoxLayout()
    video_widget = VideoOpenGLWidget()
    layout.addWidget(video_widget)
    window.setLayout(layout)

    player = FFmpegRTSPPlayer(RTSP_URL, WIDTH, HEIGHT)

    frame_count = [0]

    def on_frame(q_image):
        frame_count[0] += 1
        if frame_count[0] % 30 == 0:
            print(f"received {frame_count[0]} frames")
        video_widget.update_frame(q_image)

    player.frame_updated.connect(on_frame)
    player.error_occurred.connect(lambda msg: print(f"error: {msg}"))
    player.start()

    window.show()
    print(f"connecting to {RTSP_URL} ...")
    print("OpenGL mode will be logged by VideoOpenGLWidget at startup.")

    try:
        sys.exit(app.exec())
    finally:
        player.stop()
        player.wait(2000)
        video_widget.cleanup()
