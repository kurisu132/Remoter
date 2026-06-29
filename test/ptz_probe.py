"""
PTZ API 探针 — 逐个测试命令格式，打印完整响应。
用法：uv run python test/ptz_probe.py
"""
import sys, time, json
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from api.ptz_control import PTZControlClient

HOST = "192.168.1.36"
c = PTZControlClient(host=HOST, username="admin", password="123456", timeout=3.0)

def send(label, cmd, is_stop, speed=5):
    print(f"\n[{label}]  Cmd={cmd}  IsStop={is_stop}  Speed={speed}")
    ok, resp = c.ptz_control(cmd=cmd, is_stop=is_stop, speed=speed)
    print(f"  → ok={ok}  resp={resp}")
    return ok

print("=" * 50)
print("step 1: 上转 1 秒")
send("pan_up START",  cmd=21, is_stop=0)
time.sleep(1)

print("\nstep 2: 尝试通用停止 cmd=20,IsStop=1")
send("generic STOP",  cmd=20, is_stop=1)
time.sleep(0.5)

print("\nstep 3: 再次上转 1 秒")
send("pan_up START",  cmd=21, is_stop=0)
time.sleep(1)

print("\nstep 4: 方向停止 cmd=21,IsStop=1")
send("directional STOP", cmd=21, is_stop=1)
time.sleep(0.5)

print("\nstep 5: 左转 1 秒")
send("pan_left START", cmd=23, is_stop=0)
time.sleep(1)

print("\nstep 6: 左转方向停止 cmd=23,IsStop=1")
send("pan_left STOP",  cmd=23, is_stop=1)

print("\n" + "=" * 50)
print("观察摄像头实际动作，对照上面的日志判断哪种 stop 格式有效。")
