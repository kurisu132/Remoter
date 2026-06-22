"""
STM32 串口模拟器 — 向主应用发送串口控制帧（SYNC 0xAB，v1，9 字节）

Linux / OrangePi（推荐 --pty，无需 socat）：
    uv run python test/sim_stm32.py --pty
    # 自动在 /tmp/stm32_app 建软链接，config.toml: stm32_port = "/tmp/stm32_app"

    uv run python test/sim_stm32.py --pty --port /tmp/my_stm32

真实串口（接实际硬件替代器）：
    uv run python test/sim_stm32.py --port /dev/ttyACM1
    uv run python test/sim_stm32.py --port COM14 --mode static --left 100 --right 100
"""

import argparse
import math
import os
import signal
import struct
import sys
import time

_SYNC = 0xAB
_VERSION = 0x01
_LENGTH = 0x05

FLAG_ESTOP = 0x01
FLAG_REMOTE_ACTIVE = 0x02


def _build_frame(left: int, right: int, flags: int) -> bytes:
    left = max(-255, min(255, left))
    right = max(-255, min(255, right))
    payload = struct.pack("<BBBhhB", _SYNC, _VERSION, _LENGTH, left, right, flags)
    checksum = sum(payload) & 0xFF
    return payload + bytes([checksum])


def _decode_flags(flags: int) -> str:
    parts = []
    if flags & FLAG_ESTOP:
        parts.append("ESTOP")
    if flags & FLAG_REMOTE_ACTIVE:
        parts.append("REMOTE_ACTIVE")
    return "|".join(parts) if parts else "none"


def _ts() -> str:
    t = time.time()
    ms = int((t % 1) * 1000)
    return time.strftime(f"%H:%M:%S.{ms:03d}", time.localtime(t))


class _FdWriter:
    """os.write(fd) 的薄包装，接口与 serial.Serial 兼容。"""
    def __init__(self, fd: int):
        self._fd = fd

    def write(self, data: bytes) -> None:
        os.write(self._fd, data)

    def close(self) -> None:
        try:
            os.close(self._fd)
        except OSError:
            pass


# --- 发送模式 ---

def _mode_sine(writer, rate: int, base_flags: int) -> None:
    period = 4.0
    interval = 1.0 / rate
    seq = 0
    t0 = time.monotonic()

    while True:
        t = time.monotonic() - t0
        left = int(math.sin(2 * math.pi * t / period) * 255)
        right = int(math.sin(2 * math.pi * t / period + math.pi / 4) * 255)
        frame = _build_frame(left, right, base_flags)
        writer.write(frame)
        seq += 1
        print(
            f"[{_ts()}] 发送 #{seq:05d}"
            f"  left={left:+04d}  right={right:+04d}"
            f"  flags=0x{base_flags:02X} ({_decode_flags(base_flags)})"
        )
        time.sleep(interval)


def _mode_static(writer, rate: int, left: int, right: int, flags: int) -> None:
    interval = 1.0 / rate
    seq = 0
    frame = _build_frame(left, right, flags)

    while True:
        writer.write(frame)
        seq += 1
        print(
            f"[{_ts()}] 发送 #{seq:05d}"
            f"  left={left:+04d}  right={right:+04d}"
            f"  flags=0x{flags:02X} ({_decode_flags(flags)})"
        )
        time.sleep(interval)


def _mode_walk(writer, rate: int, base_flags: int) -> None:
    steps = [
        (2.0,   0,    0,   "静止"),
        (2.0, 200,  200,   "直行"),
        (1.0, 200,  -50,   "左转"),
        (2.0, 200,  200,   "直行"),
        (1.0, -50,  200,   "右转"),
        (1.0,   0,    0,   "停止"),
    ]
    interval = 1.0 / rate
    seq = 0

    for duration, left, right, label in steps:
        print(f"[{_ts()}] --- {label} ({duration:.0f}s) ---")
        end = time.monotonic() + duration
        frame = _build_frame(left, right, base_flags)
        while time.monotonic() < end:
            writer.write(frame)
            seq += 1
            print(
                f"[{_ts()}] 发送 #{seq:05d}"
                f"  left={left:+04d}  right={right:+04d}"
                f"  flags=0x{base_flags:02X} ({_decode_flags(base_flags)})"
            )
            time.sleep(interval)

    print(f"[{_ts()}] walk 完成，共发送 {seq} 帧")


def _open_pty(link_path: str):
    """创建 PTY 对，将 slave 端暴露为 link_path 软链接，返回 master _FdWriter。"""
    import pty as _pty
    master_fd, slave_fd = _pty.openpty()
    slave_name = os.ttyname(slave_fd)
    os.close(slave_fd)

    if os.path.lexists(link_path):
        os.unlink(link_path)
    os.symlink(slave_name, link_path)

    print(f"[STM32 模拟器] PTY 模式  {slave_name} → {link_path}")
    print(f"              config.toml: stm32_port = \"{link_path}\"")
    return _FdWriter(master_fd), link_path


def _open_serial(port: str):
    import serial
    try:
        ser = serial.Serial(port, 115200, timeout=1)
    except serial.SerialException as e:
        print(f"[错误] 无法打开串口 {port}: {e}", file=sys.stderr)
        sys.exit(1)
    return ser, None


def run(args: argparse.Namespace) -> None:
    base_flags = FLAG_REMOTE_ACTIVE
    if args.estop:
        base_flags |= FLAG_ESTOP
    if not args.active:
        base_flags &= ~FLAG_REMOTE_ACTIVE

    if args.pty:
        link_path = args.port if args.port != "COM14" else "/tmp/stm32_app"
        writer, pty_link = _open_pty(link_path)
    else:
        writer, pty_link = _open_serial(args.port)

    print(
        f"[STM32 模拟器] 模式={args.mode}  频率={args.rate} Hz  (Ctrl+C 退出)"
    )

    def _stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _stop)

    try:
        if args.mode == "sine":
            _mode_sine(writer, args.rate, base_flags)
        elif args.mode == "static":
            _mode_static(writer, args.rate, args.left, args.right, base_flags)
        elif args.mode == "walk":
            _mode_walk(writer, args.rate, base_flags)
    except KeyboardInterrupt:
        pass
    finally:
        writer.close()
        if pty_link and os.path.lexists(pty_link):
            os.unlink(pty_link)
        print(f"\n[STM32 模拟器] 已退出")


def main() -> None:
    parser = argparse.ArgumentParser(description="STM32 串口模拟器")
    parser.add_argument(
        "--pty",
        action="store_true",
        help="Linux/OrangePi：用 Python pty 建虚拟串口，无需 socat（推荐）",
    )
    parser.add_argument(
        "--port",
        default="COM14",
        help="--pty 时为软链接路径（默认 /tmp/stm32_app）；否则为串口设备（默认 COM14）",
    )
    parser.add_argument(
        "--mode",
        choices=["sine", "static", "walk"],
        default="sine",
        help="发送模式（默认 sine）",
    )
    parser.add_argument("--rate", type=int, default=50, help="发送频率 Hz（默认 50）")
    parser.add_argument("--left", type=int, default=0, help="static 模式左轮速度（默认 0）")
    parser.add_argument("--right", type=int, default=0, help="static 模式右轮速度（默认 0）")
    parser.add_argument("--estop", action="store_true", help="置 ESTOP 位")
    parser.add_argument(
        "--no-active",
        dest="active",
        action="store_false",
        default=True,
        help="清除 REMOTE_ACTIVE 位（默认已置位）",
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
