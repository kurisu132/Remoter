import requests
import hashlib
import re
import time
from typing import Tuple, Dict, Union


class PTZControlClient:
    """
    云台控制客户端（支持 HTTP Digest 认证，使用持久连接）

    功能：
        - 提供云台的上/下/左/右/停止等控制命令
        - 自动进行 Digest 认证握手
        - 每次请求耗时 ≤ 500ms
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        opaque: str = "5ccc069c403ebaf9f0171e9517f40e41",
        timeout: float = 0.2
    ):
        """
        初始化云台控制客户端。

        Args:
            host: 设备主机地址（如 "192.168.1.64"）
            username: 用户名
            password: 密码
            opaque: 可选的 opaque 参数（设备返回的验证信息）
            timeout: 每次请求超时时间（秒）
        """
        self.host = host
        self.username = username
        self.password = password
        self.opaque = opaque
        self.timeout = timeout
        self.endpoint = "/digest/frmPTZControl"

        # ✅ 持久会话，支持 Keep-Alive，提高请求效率
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "PTZControlClient/1.0",
            "Accept": "*/*"
        })

    # ------------------------------------------------------------------------------------
    # Digest 认证逻辑
    # ------------------------------------------------------------------------------------
    def _calculate_digest_header(self, method: str, uri: str, nonce: str, realm: str) -> str:
        """计算 HTTP Digest 认证头"""
        cnonce = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        ha1 = hashlib.md5(f"{self.username}:{realm}:{self.password}".encode()).hexdigest()
        ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
        response = hashlib.md5(
            f"{ha1}:{nonce}:00000001:{cnonce}:auth:{ha2}".encode()
        ).hexdigest()

        return (
            f'Digest username="{self.username}", realm="{realm}", nonce="{nonce}", uri="{uri}", '
            f'algorithm="MD5", qop="auth", nc=00000001, cnonce="{cnonce}", '
            f'response="{response}", opaque="{self.opaque}"'
        )

    # ------------------------------------------------------------------------------------
    # 请求封装
    # ------------------------------------------------------------------------------------
    def _send_ptz_request(self, payload: Dict) -> Tuple[bool, Union[str, Dict]]:
        """发送云台控制请求（带 Digest 认证流程）"""
        start_time = time.time()
        url = f"http://{self.host}{self.endpoint}"

        try:
            # Step 1: 发送无认证请求，获取 nonce/realm/opaque
            first_resp = self.session.post(url, json=payload, timeout=self.timeout)
            if first_resp.status_code != 401:
                # 某些设备可能不要求认证
                return True, first_resp.text

            # 提取 Digest 参数
            auth_header = first_resp.headers.get("WWW-Authenticate", "")
            nonce_match = re.search(r'nonce="([^"]+)"', auth_header)
            realm_match = re.search(r'realm="([^"]+)"', auth_header)
            opaque_match = re.search(r'opaque="([^"]+)"', auth_header)

            if not nonce_match or not realm_match:
                return False, f"[AuthError] 无法解析 nonce/realm | header={auth_header[:100]}"

            nonce = nonce_match.group(1)
            realm = realm_match.group(1)
            if opaque_match:
                self.opaque = opaque_match.group(1)  # ✅ 动态更新 opaque

            # Step 2: 构造 Authorization 头并重发请求
            digest_header = self._calculate_digest_header(
                method="POST", uri=self.endpoint, nonce=nonce, realm=realm
            )
            headers = {"Authorization": digest_header}
            final_resp = self.session.post(url, headers=headers, json=payload, timeout=self.timeout)

            elapsed = round(time.time() - start_time, 3)
            if elapsed > 0.5:
                return False, f"[Timeout] 请求超时（{elapsed}s > 0.5s）"

            # Step 3: 检查响应状态
            if 200 <= final_resp.status_code < 300:
                try:
                    return True, final_resp.json()
                except ValueError:
                    return True, final_resp.text
            else:
                return False, f"[HTTP {final_resp.status_code}] {final_resp.text[:100]}"

        except requests.exceptions.RequestException as e:
            elapsed = round(time.time() - start_time, 3)
            return False, f"[NetworkError] {str(e)}（耗时 {elapsed}s）"
        except Exception as e:
            return False, f"[SystemError] {str(e)}"

    # ------------------------------------------------------------------------------------
    # 云台控制业务方法
    # ------------------------------------------------------------------------------------
    def ptz_control(
        self,
        channel: int = 1,
        cmd: int = 20,
        is_stop: int = 0,
        speed: int = 5
    ) -> Tuple[bool, Union[str, Dict]]:
        """
        发送云台控制命令。

        Args:
            channel: 通道号（Ch=1）
            cmd: 控制命令号
                - 20 = 停止
                - 21 = 上转
                - 22 = 下转
                - 23 = 左转
                - 24 = 右转
            is_stop: 0=运行, 1=停止
            speed: 转动速度（建议1~7）

        Returns:
            (success, response)
        """
        payload = {
            "Ch": channel,
            "Dev": 1,
            "Type": 1,
            "Data": {
                "Cmd": cmd,
                "IsStop": is_stop,
                "Speed": speed
            }
        }
        return self._send_ptz_request(payload)

    # ------------------------------------------------------------------------------------
    # 快捷方法封装
    # ------------------------------------------------------------------------------------
    def stop(self, channel: int = 1) -> Tuple[bool, Union[str, Dict]]:
        """停止云台所有动作（cmd=20, IsStop=1）"""
        return self.ptz_control(channel=channel, cmd=20, is_stop=1)

    def pan_up(self, channel: int = 1, speed: int = 5) -> Tuple[bool, Union[str, Dict]]:
        """上转（cmd=21）"""
        return self.ptz_control(channel=channel, cmd=21, speed=speed)

    def pan_down(self, channel: int = 1, speed: int = 5) -> Tuple[bool, Union[str, Dict]]:
        """下转（cmd=22）"""
        return self.ptz_control(channel=channel, cmd=22, speed=speed)

    def pan_left(self, channel: int = 1, speed: int = 5) -> Tuple[bool, Union[str, Dict]]:
        """左转（cmd=23）"""
        return self.ptz_control(channel=channel, cmd=23, speed=speed)

    def pan_right(self, channel: int = 1, speed: int = 5) -> Tuple[bool, Union[str, Dict]]:
        """右转（cmd=24）"""
        return self.ptz_control(channel=channel, cmd=24, speed=speed)
