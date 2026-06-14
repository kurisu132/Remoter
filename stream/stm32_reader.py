"""
STM32Reader — 从 STM32 读取控制输入并通过 Qt 信号发布

帧格式（可扩展变长帧）：
  Byte 0  : 0xAB  同步头
  Byte 1  : version  当前 0x01，新增字段时递增
  Byte 2  : length   payload 字节数（不含头/version/length/checksum）
  Byte 3  : left_lo  } 左轮速 int16 小端，范围 [-255, +255]
  Byte 4  : left_hi  }
  Byte 5  : right_lo } 右轮速 int16 小端，范围 [-255, +255]
  Byte 6  : right_hi }
  Byte 7  : flags    bit0=ESTOP  bit1=REMOTE_ACTIVE  bit2~7 保留置0
  [v2+]  Byte 8+ : digital_0, digital_1 ...  后续版本追加，旧解析器自动跳过
  Byte N  : checksum  sum(bytes[0..N-1]) & 0xFF

物理接口：
  - 优先 USB CDC  (/dev/ttyACM0)
  - 备选 硬件 UART (/dev/ttyS2，需提前 enable overlay)
  两者代码层完全一致，通过构造参数 port 切换。

Ubuntu 22.04 首次使用：
  sudo usermod -aG dialout $USER  （重新登录生效）
"""
import logging
import struct
from typing import Optional

import serial
from PySide6.QtCore import QThread, Signal

logger = logging.getLogger("STM32Reader")

SYNC_BYTE    = 0xAB
MIN_FRAME    = 4    # sync + version + length + checksum（空 payload）
V1_PAYLOAD   = 5    # left(2) + right(2) + flags(1)


class ControlFrame:
    """解析后的一帧控制数据"""
    __slots__ = ("version", "left", "right", "flags", "digital")

    def __init__(self):
        self.version: int = 0
        self.left:    int = 0    # int16，-255 ~ +255
        self.right:   int = 0    # int16，-255 ~ +255
        self.flags:   int = 0    # bit0=ESTOP  bit1=REMOTE_ACTIVE
        self.digital: list[int] = []   # 未来版本追加的数字量字节

    @property
    def estop(self) -> bool:
        return bool(self.flags & 0x01)

    @property
    def remote_active(self) -> bool:
        return bool(self.flags & 0x02)

    def __repr__(self) -> str:
        return (f"ControlFrame(v={self.version} "
                f"L={self.left:+d} R={self.right:+d} "
                f"ESTOP={self.estop} REMOTE={self.remote_active})")


def _parse_frame(buf: bytes) -> Optional[ControlFrame]:
    """解析一个完整帧，返回 ControlFrame 或 None（校验失败/帧不完整）"""
    if len(buf) < MIN_FRAME or buf[0] != SYNC_BYTE:
        return None
    length = buf[2]
    total  = 3 + length + 1          # sync + version + length + payload + checksum
    if len(buf) < total:
        return None
    payload  = buf[3:3 + length]
    checksum = buf[3 + length]
    if sum(buf[:3 + length]) & 0xFF != checksum:
        logger.warning("checksum mismatch, frame dropped")
        return None

    frame         = ControlFrame()
    frame.version = buf[1]
    if length >= V1_PAYLOAD:
        frame.left  = struct.unpack_from("<h", payload, 0)[0]
        frame.right = struct.unpack_from("<h", payload, 2)[0]
        frame.flags = payload[4]
    # v2+ 数字量字节（向前兼容：旧解析器直接忽略多余字节）
    for i in range(5, length):
        frame.digital.append(payload[i])
    return frame


class STM32Reader(QThread):
    """
    持续从串口读取 STM32 控制帧，解析后通过 frame_received 信号发布。

    Signals:
        frame_received(ControlFrame)  — 每收到一个合法帧触发一次
        error_occurred(str)           — 串口异常时触发
    """
    frame_received = Signal(object)   # ControlFrame
    error_occurred = Signal(str)

    def __init__(
        self,
        port:     str   = "/dev/ttyACM0",
        baudrate: int   = 115200,
        timeout:  float = 1.0,
        parent          = None,
    ):
        super().__init__(parent)
        self._port     = port
        self._baudrate = baudrate
        self._timeout  = timeout
        self._running  = False
        self._ser: Optional[serial.Serial] = None

    # ------------------------------------------------------------------
    def run(self):
        self._running = True
        try:
            self._ser = serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                timeout=self._timeout,
            )
            logger.info(f"serial opened: {self._port} @ {self._baudrate}")
            self._read_loop()
        except serial.SerialException as e:
            msg = f"serial open failed ({self._port}): {e}"
            logger.error(msg)
            self.error_occurred.emit(msg)
        finally:
            self._close_serial()

    def _read_loop(self):
        buf = bytearray()
        while self._running:
            # 逐字节同步：丢弃直到找到 SYNC_BYTE
            byte = self._ser.read(1)
            if not byte:
                continue
            if byte[0] != SYNC_BYTE:
                continue

            # 读 version + length（2 字节）
            header = self._ser.read(2)
            if len(header) < 2:
                continue
            length = header[1]

            # 读 payload + checksum
            rest = self._ser.read(length + 1)
            if len(rest) < length + 1:
                continue

            raw = bytes([SYNC_BYTE]) + bytes(header) + bytes(rest)
            frame = _parse_frame(raw)
            if frame is not None:
                self.frame_received.emit(frame)

    def _close_serial(self):
        if self._ser and self._ser.is_open:
            try:
                self._ser.close()
            except Exception:
                pass
        self._ser = None

    def stop(self):
        """发出停止信号，由调用方负责 wait()"""
        logger.info("STM32Reader stop requested")
        self._running = False
        self._close_serial()


# ---------- 独立测试 ----------
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer

    logging.basicConfig(level=logging.DEBUG)
    app = QApplication(sys.argv)

    reader = STM32Reader(port="/dev/ttyACM0", baudrate=115200)

    def on_frame(f: ControlFrame):
        print(f)

    def on_error(msg: str):
        print(f"ERROR: {msg}")

    reader.frame_received.connect(on_frame)
    reader.error_occurred.connect(on_error)
    reader.start()

    QTimer.singleShot(10000, app.quit)
    sys.exit(app.exec())
