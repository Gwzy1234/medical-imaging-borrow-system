"""密码与令牌。

密码用 PBKDF2-HMAC-SHA256 加盐哈希后存储，数据库里永远不出现明文。
存储格式：pbkdf2_sha256$迭代次数$盐(hex)$哈希(hex)
"""

import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 120_000
SALT_BYTES = 16


def hash_password(password, iterations=DEFAULT_ITERATIONS):
    """生成可以直接存入 users.password_hash 的字符串。"""
    if not isinstance(password, str) or not password:
        raise ValueError("密码不能为空")
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{ALGORITHM}${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password, stored_hash):
    """校验明文密码与库里保存的哈希是否匹配。"""
    if not isinstance(password, str) or not isinstance(stored_hash, str):
        return False
    parts = stored_hash.split("$")
    if len(parts) != 4 or parts[0] != ALGORITHM:
        return False
    _, iterations_text, salt_hex, digest_hex = parts
    try:
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(computed.hex(), digest_hex)


def new_token():
    """生成登录令牌（URL 安全的随机字符串）。"""
    return secrets.token_urlsafe(32)
