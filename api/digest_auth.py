import re
import hashlib
from urllib.parse import urlparse
import requests
from requests.auth import HTTPDigestAuth
import time

def digest_auth_request(config):
    """
    稳健版 Digest 认证函数（可在 GUI 子线程中调用）

    :param config: dict，包含 url, username, password, http_method, request_data, headers, timeout
    :return: tuple (success: bool, result)
        - success=True: 返回 requests.Response
        - success=False: 返回详细错误信息字符串
    """
    url = config["url"]
    username = config["username"]
    password = config["password"]
    method = config.get("http_method", "POST").upper()
    data = config.get("request_data", {})
    headers = config.get("headers", {})
    timeout = config.get("timeout", 10)

    for attempt in range(3):
        try:
            # --------------------------
            # 第一次请求：获取 WWW-Authenticate
            # --------------------------
            first_response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                timeout=timeout
            )
            if first_response.status_code != 401:
                return True, first_response  # 无需认证直接返回

            # 获取认证头
            auth_header = first_response.headers.get("WWW-Authenticate", "")
            if not auth_header:
                return False, "服务器未返回认证信息（缺少WWW-Authenticate头）"

            # 解析认证参数
            try:
                auth_params = {
                    "realm": re.findall(r'realm="([^"]+)"', auth_header)[0],
                    "nonce": re.findall(r'nonce="([^"]+)"', auth_header)[0],
                    "qop": re.findall(r'qop="([^"]+)"', auth_header)[0],
                    "opaque": re.findall(r'opaque="([^"]+)"', auth_header)[0]
                }
            except IndexError:
                return False, f"认证头格式错误，原始头：{auth_header}"

            # --------------------------
            # 计算Digest认证参数
            # --------------------------
            uri = urlparse(url).path
            cnonce = hashlib.md5(str(hash(url)).encode()).hexdigest()[:8]
            nc = "00000001"
            ha1 = hashlib.md5(f"{username}:{auth_params['realm']}:{password}".encode()).hexdigest()
            ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
            response_digest = hashlib.md5(f"{ha1}:{auth_params['nonce']}:{nc}:{cnonce}:{auth_params['qop']}:{ha2}".encode()).hexdigest()

            # 构造认证头
            final_headers = headers.copy()
            final_headers["Authorization"] = (
                f'Digest username="{username}", realm="{auth_params["realm"]}", '
                f'nonce="{auth_params["nonce"]}", uri="{uri}", '
                f'response="{response_digest}", cnonce="{cnonce}", '
                f'opaque="{auth_params["opaque"]}", qop={auth_params["qop"]}, nc={nc}'
            )

            # --------------------------
            # 第二次请求：带认证头
            # --------------------------
            final_response = requests.request(
                method=method,
                url=url,
                headers=final_headers,
                json=data,
                timeout=timeout
            )

            if 200 <= final_response.status_code < 300:
                return True, final_response
            else:
                return False, f"认证失败，状态码 {final_response.status_code}，响应内容前200字符：{final_response.text[:200]}"

        except requests.exceptions.ConnectTimeout:
            if attempt < 2:
                time.sleep(0.5)
                continue
            return False, "连接超时（ConnectTimeout）"
        except requests.exceptions.ReadTimeout:
            if attempt < 2:
                time.sleep(0.5)
                continue
            return False, "读取超时（ReadTimeout）"
        except requests.exceptions.ConnectionError as e:
            return False, f"网络错误：{e}"
        except Exception as e:
            return False, f"系统错误：{e}"

    return False, "重试3次仍失败"


# --------------------------
# 测试功能（可直接运行模块测试）
# --------------------------
if __name__ == "__main__":
    test_config = {
        "url": "http://192.168.1.36:80/digest/frmUserLogin",
        "username": "admin",
        "password": "123456",
        "http_method": "POST",
        "request_data": {"Type": 0, "Ch": 0, "Data": {}},
        "headers": {
            "User-Agent": "curl/4.7.1",
            "Content-Type": "application/json; charset=utf-8",
            "Accept-Encoding": "gzip"
        },
        "timeout": 10
    }

    success, result = digest_auth_request(test_config)
    if success:
        print("认证成功！状态码：", result.status_code)
        print(result.text[:500])
    else:
        print("认证失败：", result)
