"""
登入憑證管理（backend/session_tokens.py）
==========================================
提供最簡的 token 管理（記憶體 dict）：

- 登入成功時由 auth.py 呼叫 create_token(member_id) 產生一組隨機 token
- 之後前端在所有需要身分的請求帶上 Authorization: Bearer <token>
- 後端透過 get_member_id(token) 查出目前登入的會員，作為身分依據
- 登出時呼叫 delete_token(token) 讓該 token 失效

注意：此實作以記憶體儲存，伺服器重啟後 token 全部失效（會員需重新登入）。
適合示範／開發用；正式環境可改以資料庫或 Redis 保存。
"""

import secrets

# token → member_id 的對應表（單一程序內共享）
_TOKENS: dict[str, int] = {}


def create_token(member_id: int) -> str:
    """產生一組新的隨機 token 並與會員編號綁定，回傳 token"""
    token = secrets.token_urlsafe(32)
    _TOKENS[token] = member_id
    return token


def get_member_id(token: str) -> int | None:
    """依 token 回傳會員編號；token 無效或不存在時回傳 None"""
    return _TOKENS.get(token)


def delete_token(token: str) -> None:
    """使 token 失效（登出時呼叫）；token 不存在時不做事"""
    _TOKENS.pop(token, None)
