"""
UDPControlSender — 以 50 Hz 将 STM32 控制输入封装为 REMOTE_PROTOCOL_v1 帧
并通过 UDP 发往工控机。

REMOTE_PROTOCOL_v1 帧格式（8 字节）：
  Byte 0 : 0x12   header
  Byte 1 : 0x10   CMD = MOTION
  Byte 2 : left_lo
  Byte 3 : left_hi
  Byte 4 : right_lo
  Byte 5 : right_hi
  Byte 6 : flags   (bit0=ESTOP  bit1=REMOTE_ACTIVE)
  Byte 7 : checksum = sum(bytes[0..6]) & 0xFF

使用方式：
  sender = UDPControlSender(target_ip="192.168.1.11", target_port=9000)
  sender.start()
  # 收到 ControlFrame 时：
  sender.update(frame)
  # 关闭时：
  sender.stop(); sender.wait(1000)

配置文件：~/.vlink/config.json
  { "target_ip": "192.168.1.11", "target_port": 9000 }
"""
import json
import logging
import socket
import struct
import threading
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal

from stream.stm32_reader import ControlFrame

logger = logging.getLogger("UDPControlSender")

_FRAME_HEADER  = 0x12
_CMD_MOTION    = 0x10
_SEND_HZ       = 50
_SEND_INTERVAL = 1.0 / _SEND_HZ

CONFIG_PATH = Path.home() / ".vlink" / "config.json"
def _default_stm32_port() -> str:
    import platform
    return "COM3" if platform.system() == "Windows" else "/dev/ttyACM0"


DEFAULT_CONFIG = {
    "target_ip": "192.168.1.11",
    "target_port": 9000,
    "camera_host": "192.168.1.36",
    "camera_user": "admin",
    "camera_pass": "123456",
    "stm32_port": _default_stm32_port(),
}


def load_config() -> dict:
    """读取配置文件，不存在时写入默认值并返回"""
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception as e:
            logger.warning(f"config read error, using default: {e}")
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    logger.info(f"config saved: {cfg}")


def build_udp_frame(left: int, right: int, flags: int) -> bytes:
    """将控制值打包为 REMOTE_PROTOCOL_v1 的 8 字节 UDP 帧"""
    payload = struct.pack(
        "<BBhhB",          # header, cmd, left(int16), right(int16), flags
        _FRAME_HEADER,
        _CMD_MOTION,
        left,
        right,
        flags,
    )
    checksum = sum(payload) & 0xFF
    return payload + bytes([checksum])


class UDPControlSender(QThread):
    """
    以固定 50 Hz 发送控制帧的后台线程。

    外部调用 update(frame) 更新当前控制值；若长时间未调用 update，
    线程仍会按 50 Hz 发送最后一帧（保持心跳），符合工控机端失联超时机制。

    Signals:
        send_error(str)  — UDP 发送异常时触发
    """
    send_error = Signal(str)

    def __init__(
        self,
        target_ip:   Optional[str] = None,
        target_port: Optional[int] = None,
        parent=None,
    ):
        super().__init__(parent)
        cfg = load_config()
        self._ip   = target_ip   or cfg["target_ip"]
        self._port = target_port or cfg["target_port"]
        self._lock  = threading.Lock()
        self._left:  int = 0
        self._right: int = 0
        self._flags: int = 0
        self._running = False
        logger.info(f"UDPControlSender target: {self._ip}:{self._port}")

    # ------------------------------------------------------------------
    def update(self, frame: ControlFrame) -> None:
        """由 STM32Reader.frame_received 信号调用，线程安全"""
        with self._lock:
            self._left  = frame.left
            self._right = frame.right
            self._flags = frame.flags

    def set_target(self, ip: str, port: int = 9000) -> None:
        """运行时更换目标地址（UI 中修改 IP 后调用）"""
        self._ip   = ip
        self._port = port
        save_config({"target_ip": ip, "target_port": port})
        logger.info(f"target updated: {ip}:{port}")

    @property
    def target_ip(self) -> str:
        return self._ip

    # ------------------------------------------------------------------
    def run(self):
        self._running = True
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            logger.info(f"UDP sender started → {self._ip}:{self._port} @ {_SEND_HZ} Hz")
            while self._running:
                t0 = time.monotonic()
                with self._lock:
                    left, right, flags = self._left, self._right, self._flags
                frame_bytes = build_udp_frame(left, right, flags)
                try:
                    sock.sendto(frame_bytes, (self._ip, self._port))
                except OSError as e:
                    msg = f"UDP send error: {e}"
                    logger.error(msg)
                    self.send_error.emit(msg)
                elapsed = time.monotonic() - t0
                sleep_t = _SEND_INTERVAL - elapsed
                if sleep_t > 0:
                    time.sleep(sleep_t)
        finally:
            sock.close()
            logger.info("UDP sender stopped")

    def stop(self):
        """发出停止信号，由调用方负责 wait()"""
        logger.info("UDPControlSender stop requested")
        self._running = False


# ---------- 独立测试 ----------
if __name__ == "__main__":
    import sys
    import time
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer

    logging.basicConfig(level=logging.DEBUG)
    app = QApplication(sys.argv)

    sender = UDPControlSender(target_ip="127.0.0.1", target_port=9000)

    # 模拟一个匀速前进的 ControlFrame
    class _FakeFrame:
        left = 100; right = 100; flags = 0x02   # REMOTE_ACTIVE

    sender.update(_FakeFrame())
    sender.start()
    print("sending test frames to 127.0.0.1:9000 for 5 seconds ...")
    QTimer.singleShot(5000, lambda: (sender.stop(), app.quit()))
    sys.exit(app.exec())
