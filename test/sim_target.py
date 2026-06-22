"""
工控机 UDP 接收模拟器 — 解析并打印 REMOTE_PROTOCOL_v1 帧

用法：
    uv run python test/sim_target.py
    uv run python test/sim_target.py --port 9000 --bind 0.0.0.0
"""

import argparse
import signal
import socket
import struct
import sys
import time

_HEADER = 0x12
_CMD_MOTION = 0x10
_FRAME_LEN = 8
_STATS_INTERVAL = 5.0


def _decode_flags(flags: int) -> str:
    parts = []
    if flags & 0x01:
        parts.append("ESTOP")
    if flags & 0x02:
        parts.append("REMOTE_ACTIVE")
    return "|".join(parts) if parts else "none"


def _ts() -> str:
    t = time.time()
    ms = int((t % 1) * 1000)
    return time.strftime(f"%H:%M:%S.{ms:03d}", time.localtime(t))


def run(bind_addr: str, port: int) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((bind_addr, port))
    sock.settimeout(1.0)

    print(f"[UDP 接收器] 监听 {bind_addr}:{port} ...  (Ctrl+C 退出)")

    total = 0
    bad = 0
    stats_start = time.monotonic()

    running = True

    def _stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, _stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _stop)

    while running:
        try:
            data, addr = sock.recvfrom(64)
        except socket.timeout:
            now = time.monotonic()
            if now - stats_start >= _STATS_INTERVAL:
                elapsed = now - stats_start
                hz = (total / elapsed) if elapsed > 0 else 0.0
                print(
                    f"[{_ts()}] 统计 {elapsed:.1f}s: "
                    f"收到 {total} 帧 / 坏帧 {bad} / 均频 {hz:.1f} Hz"
                )
                total = 0
                bad = 0
                stats_start = now
            continue

        total += 1

        if len(data) != _FRAME_LEN:
            bad += 1
            print(f"[{_ts()}]  长度错误: 期望 {_FRAME_LEN}B 实收 {len(data)}B  ✗")
            continue

        header, cmd, left, right, flags, checksum = struct.unpack("<BBhhBB", data)
        expected_cs = sum(data[:7]) & 0xFF
        cs_ok = checksum == expected_cs

        if not cs_ok:
            bad += 1

        flag_str = _decode_flags(flags)
        cs_mark = "✓" if cs_ok else f"✗ BAD (期望 0x{expected_cs:02X} 实收 0x{checksum:02X})"

        print(
            f"[{_ts()}]  left={left:+04d}  right={right:+04d}"
            f"  flags=0x{flags:02X} ({flag_str})"
            f"  {cs_mark}"
        )

        now = time.monotonic()
        if now - stats_start >= _STATS_INTERVAL:
            elapsed = now - stats_start
            hz = (total / elapsed) if elapsed > 0 else 0.0
            print(
                f"[{_ts()}] 统计 {elapsed:.1f}s: "
                f"收到 {total} 帧 / 坏帧 {bad} / 均频 {hz:.1f} Hz"
            )
            total = 0
            bad = 0
            stats_start = now

    sock.close()
    print(f"\n[UDP 接收器] 已退出")


def main() -> None:
    parser = argparse.ArgumentParser(description="工控机 UDP 接收模拟器")
    parser.add_argument("--port", type=int, default=9000, help="监听端口（默认 9000）")
    parser.add_argument("--bind", default="0.0.0.0", help="绑定地址（默认 0.0.0.0）")
    args = parser.parse_args()
    run(args.bind, args.port)


if __name__ == "__main__":
    main()
