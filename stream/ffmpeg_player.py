import logging
import subprocess as sp
import numpy as np
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QImage, QPixmap  # 关键：导入QPixmap

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FFmpeg-RTSP-Player")


class FFmpegRTSPPlayer(QThread):
    """基于FFmpeg的RTSP拉流线程，输出QImage到UI"""
    frame_updated = Signal(QImage)  # 发送QImage信号（UI线程显示）
    error_occurred = Signal(str)    # 错误信息信号

    def __init__(self, rtsp_url: str, width=1280, height=720, parent=None):
        super().__init__(parent)
        self.rtsp_url = rtsp_url  # RTSP流地址
        self.width = width        # 视频宽度（默认1280）
        self.height = height      # 视频高度（默认720）
        self._is_running = False  # 线程运行标志
        self._process = None      # FFmpeg子进程句柄

    def run(self) -> None:
        """启动FFmpeg拉流，读取帧并发送到UI"""
        self._is_running = True
        # FFmpeg命令行（关键：TCP传输、RGB24格式、原始视频输出）
        ffmpeg_cmd = [
            "ffmpeg",
            "-rtsp_transport", "tcp",  # TCP传输（网络不稳定时推荐）
            "-i", self.rtsp_url,       # 输入RTSP地址
            "-pix_fmt", "rgb24",       # 输出RGB格式（Qt直接支持）
            "-s", f"{self.width}x{self.height}",  # 分辨率（与UI视频框匹配）
            "-f", "rawvideo",          # 原始视频流输出
            "-an", "-sn",              # 忽略音频和字幕
            "-vcodec", "rawvideo",     # 强制原始视频编码
            "-loglevel", "error",      # 仅输出错误日志（避免冗余信息）
            "-"                        # 输出到管道
        ]

        try:
            # 启动FFmpeg子进程（管道读取输出）
            self._process = sp.Popen(
                ffmpeg_cmd,
                stdout=sp.PIPE,
                stderr=sp.PIPE,
                bufsize=self.width * self.height * 3  # 缓冲区=1帧大小
            )

            frame_size = self.width * self.height * 3  # 每帧字节数（RGB24=3字节/像素）

            while self._is_running:
                # 读取一帧数据（阻塞直到有数据）
                frame_data = self._process.stdout.read(frame_size)
                if not frame_data:
                    self.error_occurred.emit("流已断开或无数据（检查RTSP地址）")
                    break

                # 转换为numpy数组（RGB格式）
                frame = np.frombuffer(frame_data, dtype=np.uint8).reshape(
                    (self.height, self.width, 3)
                )

                # 转为QImage（发送到UI线程显示）
                q_image = QImage(
                    frame.data,
                    self.width,
                    self.height,
                    self.width * 3,  # 每行字节数（width*3）
                    QImage.Format_RGB888
                )
                self.frame_updated.emit(q_image)

        except Exception as e:
            self.error_occurred.emit(f"拉流失败: {str(e)}")
        finally:
            self._stop_process()  # 确保进程终止
            self._is_running = False
            logger.info("FFmpeg拉流线程已停止")

    def _stop_process(self):
        """终止FFmpeg子进程（防止资源泄露）"""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            self._process.wait()
            logger.info("FFmpeg子进程已终止")

    def stop(self):
        """停止线程（外部调用，如窗口关闭时）"""
        self._is_running = False
        self._stop_process()
        self.wait()  # 等待线程退出


# 独立测试：直接运行此文件可验证FFmpeg拉流功能
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication, QLabel, QWidget, QVBoxLayout

    app = QApplication(sys.argv)
    window = QWidget()
    window.setWindowTitle("FFmpeg RTSP测试")
    layout = QVBoxLayout(window)
    widget = QLabel("加载中...")
    widget.setAlignment(Qt.AlignCenter)  # 图像居中
    layout.addWidget(widget)
    window.resize(800, 600)  # 窗口大小（与视频分辨率比例匹配）
    window.show()

    # 替换为你的RTSP地址
    player = FFmpegRTSPPlayer("rtsp://192.168.0.36:554/ch01.264", width=800, height=600)
    player.frame_updated.connect(
        lambda img: widget.setPixmap(QPixmap.fromImage(img))
    )
    player.error_occurred.connect(lambda err: print(f"错误: {err}"))
    player.start()

    sys.exit(app.exec())