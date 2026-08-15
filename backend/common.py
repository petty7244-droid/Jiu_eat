"""
共用工具函式（backend/common.py）
====================================
本模組提供整個後端共用的輔助函式，包含：

1. 時間處理（定義於 database.py，此處重新匯出使用）
   - taipei_now()      ：取得目前台北時間（naive datetime，無時區資訊）
   - to_naive_taipei() ：把帶有時區的 datetime 轉為 Taipei 時區的 naive datetime

2. 密碼安全
   - hash_password()   ：使用 PBKDF2-SHA256 將明文密碼雜湊成「salt:digest」格式
   - verify_password() ：比對使用者輸入的密碼與儲存的雜湊值是否一致

3. 資料庫查詢輔助
   - member_or_404()   ：依 ID 查會員，找不到直接丟 404
   - activity_or_404() ：依 ID 查活動，找不到直接丟 404

4. JSON 序列化
   - activity_json()   ：把 Activity 資料庫物件轉成 API 回應用的 dict
   - application_json()：把 Application 資料庫物件轉成 API 回應用的 dict

5. 業務驗證
   - validate_activity()：檢查活動時間與報名截止時間是否合乎邏輯
"""

import hashlib        # 提供 PBKDF2 密碼雜湊演算法
import hmac           # 提供安全的常時比較（constant-time compare）
import os             # 提供亂數（產生密碼鹽值）
from typing import Optional                          # 型別提示：可選參數

from fastapi import Depends, HTTPException, Header      # 用於身分驗證與標準化 HTTP 錯誤
from sqlalchemy.orm import Session     # SQLAlchemy 的 SQL Server Session 型別

from . import models                   # 匯入 ORM 模型（Member / Activity / Application）
from .database import get_db           # 資料庫 Session 依賴（供身分驗證使用）
from .database import taipei_now, to_naive_taipei   # 時間工具（統一由 database 提供）
from .session_tokens import get_member_id   # token 查會員編號


# ── 密碼雜湊 ──────────────────────────────────────────────

def hash_password(password: str) -> str:
    """
    使用 PBKDF2-SHA256 雜湊密碼，回傳「salt:digest」格式字串
    - salt：隨機產生的 16 bytes 鹽值（hex 字串）
    - digest：PBKDF2 疊代 120,000 次後的雜湊結果（hex 字串）
    - 加鹽的目的是防止彩虹表攻擊，讓相同密碼產生不同雜湊
    """
    salt = os.urandom(16)                                # 隨機產生 16 bytes 鹽值
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return f"{salt.hex()}:{digest.hex()}"                # 回傳格式：hex(salt):hex(digest)


def verify_password(password: str, stored: str) -> bool:
    """
    驗證密碼是否與儲存的雜湊值匹配
    - 從 stored 拆出 salt 與 digest 兩部分
    - 用相同的鹽值與參數重新計算雜湊，再與儲存值比較
    - 使用 hmac.compare_digest 進行常時比較，避免「時序攻擊」
    - 格式錯誤（沒有冒號分隔）時回傳 False
    """
    try:
        salt_hex, digest_hex = stored.split(":", 1)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), 120_000
        )
        return hmac.compare_digest(digest.hex(), digest_hex)  # 常時比較，防時序攻擊
    except ValueError:
        return False  # stored 格式不符時視為驗證失敗


# ── 身分驗證 ─────────────────────────────────────────────

def get_current_member(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> models.Member:
    """
    從 Authorization: Bearer <token> 標頭解析目前登入的會員
    - token 無效或會員不存在時丟出 HTTPException(401)，要求先登入
    - 回傳 Member 物件，供路由使用目前登入者的身分
    """
    token = authorization.removeprefix("Bearer ").strip()
    member_id = get_member_id(token) if token else None
    if member_id is None:
        raise HTTPException(401, "請先登入")
    member = db.get(models.Member, member_id)
    if not member:
        raise HTTPException(401, "請先登入")
    return member


def get_optional_member(authorization: str = Header(default=""), db: Session = Depends(get_db)):
    """
    從 Authorization: Bearer <token> 標頭解析目前登入的會員（可選）
    - token 無效、未提供或會員不存在時回傳 None（不強制登入）
    - 供「未登入也可查看、登入後多帶資訊」的端點使用
    """
    token = authorization.removeprefix("Bearer ").strip()
    member_id = get_member_id(token) if token else None
    if member_id is None:
        return None
    return db.get(models.Member, member_id)


# ── 資料查詢輔助 ──────────────────────────────────────────

def member_or_404(db: Session, member_id: int):
    """
    查詢會員，找不到則回傳 404 錯誤
    - 以主鍵 member_id 直接查詢 Member 資料表
    - 不存在時丟出 HTTPException(404, "找不到會員")
    """
    member = db.get(models.Member, member_id)
    if not member:
        raise HTTPException(404, "找不到會員")
    return member


def activity_or_404(db: Session, activity_id: int):
    """
    查詢活動，找不到則回傳 404 錯誤
    - 以主鍵 activity_id 直接查詢 Activity 資料表
    - 不存在時丟出 HTTPException(404, "找不到活動")
    """
    activity = db.get(models.Activity, activity_id)
    if not activity:
        raise HTTPException(404, "找不到活動")
    return activity


def with_row_lock(query, model):
    """
    為查詢加上列鎖（row lock），用於串行化並發寫入（報名／核准），避免超賣：
    - SQL Server 不支援 SELECT ... FOR UPDATE，SQLAlchemy 對其 with_for_update()
      會「靜默忽略」而不會報錯，等於沒鎖；因此改用 SQL Server 的
      資料表提示 WITH (UPDLOCK, HOLDLOCK)（搭配單列掃描，鎖定資料列，
      並將鎖持有到交易結束）。
    - 其他資料庫（PostgreSQL/MySQL/SQLite 等）沿用標準 with_for_update()。
    """
    if query.session.get_bind().dialect.name == "mssql":
        return query.with_hint(model, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
    return query.with_for_update()


# ── JSON 轉換 ─────────────────────────────────────────────

def activity_json(activity: models.Activity, member_id: Optional[int] = None) -> dict:
    """
    將 Activity ORM 物件轉換為 API 回應用的 dict
    - approved：統計所有申請中狀態為「approved」的人數（已核准人數）
    - 若傳入 member_id，會額外附上該會員對這個活動的申請資訊
      （my_application_id、my_application_status），方便前端顯示申請狀態
    """
    approved = sum(x.status == "approved" for x in activity.applications)  # 統計已核准人數
    result = {
        "id": activity.id, "organizer_id": activity.organizer_id,           # 活動編號、發起人編號
        "organizer_name": activity.organizer.display_name, "title": activity.title,  # 發起人名、活動名稱
        "description": activity.description, "category": activity.category, # 說明、分類
        "city": activity.city, "location_name": activity.location_name,     # 城市、地點
        "activity_date": activity.activity_date, "deadline": activity.deadline,     # 活動時間、截止時間
        "max_participants": activity.max_participants, "approved_count": approved,  # 人數上限、已核准人數
        "image_url": activity.image_url, "status": activity.status,         # 封面圖、狀態
        "created_at": activity.created_at,                                  # 建立時間
    }
    result["my_application_id"] = None      # 預設沒有我的申請編號
    result["my_application_status"] = None  # 預設沒有我的申請狀態
    if member_id:
        # 從該活動的所有申請中，找出屬於這個會員的申請
        app = next((a for a in activity.applications if a.member_id == member_id), None)
        if app:
            result["my_application_id"] = app.id            # 我的申請編號
            result["my_application_status"] = app.status    # 我的申請狀態
    return result


def application_json(application: models.Application) -> dict:
    """
    將 Application ORM 物件轉換為 API 回應用的 dict
    - member_name / activity_title 透過關聯物件取出發起人與活動的名稱
    """
    return {
        "id": application.id, "activity_id": application.activity_id,   # 申請編號、活動編號
        "member_id": application.member_id,                             # 申請人編號
        "member_name": application.member.display_name,                 # 申請人顯示名稱
        "activity_title": application.activity.title, "message": application.message,  # 活動名稱、留言
        "status": application.status, "created_at": application.created_at,            # 狀態、申請時間
    }


def notification_json(notification: models.Notification) -> dict:
    """
    將 Notification ORM 物件轉換為 API 回應用的 dict
    - activity_title 透過關聯物件取出活動名稱
    """
    return {
        "id": notification.id, "member_id": notification.member_id,   # 通知編號、收件人編號
        "activity_id": notification.activity_id,                       # 相關活動編號
        "activity_title": notification.activity.title,                 # 相關活動名稱
        "message": notification.message,                               # 通知內容
        "is_read": notification.is_read,                               # 是否已讀
        "created_at": notification.created_at,                         # 通知時間
    }


# ── 活動資料驗證 ──────────────────────────────────────────

def validate_activity(data) -> None:
    """
    驗證活動時間與截止時間的合理性
    - 活動時間必須晚於現在（不能建立過去時間的活動）
    - 報名截止時間必須早於活動時間
    - 不符合條件時丟出 HTTPException(400)，回傳中文錯誤訊息
    """
    ad = to_naive_taipei(data.activity_date)   # 活動時間（統一為台北時區）
    dl = to_naive_taipei(data.deadline)        # 報名截止時間（統一為台北時區）
    if dl <= taipei_now():
        raise HTTPException(400, "報名截止時間必須晚於目前時間")
    if ad <= taipei_now():
        raise HTTPException(400, "活動時間必須晚於目前時間")
    if dl >= ad:
        raise HTTPException(400, "報名截止時間必須早於活動時間")
