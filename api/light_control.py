import requests
import hashlib
import re
import time
from typing import Tuple


class LightControlClient:
    """补光灯控制客户端（优化Digest认证状态同步，严格控制耗时≤500ms）"""

    def __init__(self, host: str, username: str, password: str, opaque: str = "5ccc069c403ebaf9f0171e9517f40e41"):
        self.host = host
        self.username = username
        self.password = password
        self.opaque = opaque  # 设备固定Opaque值（若动态变化需从响应头获取）
        self.timeout = 0.2  # 单次网络超时（200ms，两次请求≈400ms，预留100ms设备响应）

    def _calculate_digest(self, method: str, uri: str, nonce: str, realm: str) -> str:
        """计算Digest认证头（每次请求独立计算，nc从1开始）"""
        # 1. 生成随机cnonce（每次请求不同）
        cnonce = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        # 2. 计算HA1、HA2、response（nc固定为1，因每次请求重新获取nonce）
        ha1 = hashlib.md5(f"{self.username}:{realm}:{self.password}".encode()).hexdigest()
        ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
        response = hashlib.md5(
            f"{ha1}:{nonce}:00000001:{cnonce}:auth:{ha2}".encode()  # nc固定为00000001（十进制）
        ).hexdigest()
        # 3. 构造Authorization头
        return (
            f'Digest username="{self.username}", realm="{realm}", nonce="{nonce}", uri="{uri}", '
            f'algorithm="MD5", qop="auth", nc=00000001, cnonce="{cnonce}", '
            f'response="{response}", opaque="{self.opaque}"'
        )

    def _send_single_request(self, payload: dict) -> Tuple[bool, str]:
        """发送单次控制请求（完整Digest认证流程，独立无状态）"""
        start_time = time.time()
        endpoint = "/digest/frmIotLightCfg"
        url = f"http://{self.host}{endpoint}"
        headers = {"Content-Type": "application/json", "User-Agent": "LightControlClient/1.0"}

        try:
            # 步骤1：发送无认证请求，获取nonce和realm（必走步骤，无法跳过）
            with requests.Session() as session:  # 每次请求用新会话，避免状态干扰
                # 第1次请求：无认证，触发401获取nonce
                first_resp = session.post(
                    url, headers=headers, json=payload, timeout=self.timeout
                )
                if first_resp.status_code != 401:
                    return True, first_resp.text  # 设备无需认证（特殊情况，按成功处理）

                # 解析nonce和realm（关键：每次请求必须重新获取，避免nonce过期）
                auth_header = first_resp.headers.get("WWW-Authenticate", "")
                nonce_match = re.search(r'nonce="([^"]+)"', auth_header)
                realm_match = re.search(r'realm="([^"]+)"', auth_header)
                if not nonce_match or not realm_match:
                    return False, f"解析认证头失败: {auth_header[:100]}"
                nonce = nonce_match.group(1)
                realm = realm_match.group(1)

                # 步骤2：计算认证头，发送最终请求
                headers["Authorization"] = self._calculate_digest("POST", endpoint, nonce, realm)
                final_resp = session.post(
                    url, headers=headers, json=payload, timeout=self.timeout
                )

                # 检查总耗时是否超过500ms
                if time.time() - start_time > 0.5:
                    return False, f"超时（总耗时{time.time() - start_time:.2f}s>500ms）"

                # 检查响应状态
                if 200 <= final_resp.status_code < 300:
                    return True, final_resp.text
                else:
                    return False, f"设备拒绝: 状态码{final_resp.status_code}, 响应:{final_resp.text[:100]}"

        except requests.exceptions.RequestException as e:
            return False, f"网络错误: {str(e)}（耗时{time.time() - start_time:.2f}s）"
        except Exception as e:
            return False, f"系统错误: {str(e)}（耗时{time.time() - start_time:.2f}s）"

    # ------------------------------ 业务方法（精简参数，确保独立性） ------------------------------
    def turn_light_on(self, channel: int = 1, brightness: int = 100) -> Tuple[bool, str]:
        """开灯：仅传递必要参数，每次调用独立认证"""
        payload = {
            "Ch": channel,
            "Dev": 1,
            "Type": 1,
            "Data": {"Control": 1, "Brightness": brightness, "Mode": "Warm"}  # 仅必要参数
        }
        return self._send_single_request(payload)

    def turn_light_off(self, channel: int = 1) -> Tuple[bool, str]:
        """关灯：仅传递Control=0，无冗余参数"""
        payload = {
            "Ch": channel,
            "Dev": 1,
            "Type": 1,
            "Data": {"Control": 0}  # 仅关闭控制参数，其他不传递
        }
        return self._send_single_request(payload)


# ------------------------------ 测试代码（验证成功率和耗时） ------------------------------
if __name__ == "__main__":
    # 设备配置（替换为实际参数）
    client = LightControlClient(
        host="192.168.1.36",
        username="admin",
        password="123456",
        opaque="5ccc069c403ebaf9f0171e9517f40e41"  # 从设备WWW-Authenticate头获取
    )

    # 连续测试3次开关灯，验证稳定性
    for i in range(3):
        print(f"\n=== 第{i + 1}次测试 ===")
        # 开灯测试
        start = time.time()
        success, msg = client.turn_light_on(brightness=80)
        print(f"开灯: {'成功' if success else '失败'}, 耗时: {(time.time() - start) * 1000:.2f}ms, 响应: {msg[:50]}")

        # 等待1秒后关灯（避免设备指令冲突）
        time.sleep(1)
        start = time.time()
        success, msg = client.turn_light_off()
        print(f"关灯: {'成功' if success else '失败'}, 耗时: {(time.time() - start) * 1000:.2f}ms, 响应: {msg[:50]}")