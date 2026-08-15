"""
Pydantic 資料驗證模型（backend/schemas.py）
=============================================
本模組使用 Pydantic 定義 API 的請求與回應資料結構：

- 請求（Request）類別：MemberRegister、LoginRequest、MemberUpdate、
  ActivityCreate、ActivityUpdate、ApplicationCreate
  → 負責驗證前端送來的資料格式（型別、長度、必填與否）

- 回應（Response）類別：Member、LoginResponse、Activity、Application、Recommendation
  → 負責定義 API 回傳資料的格式，搭配 ConfigDict(from_attributes=True)
    可直接將 ORM 物件轉為回應結構
"""

from datetime import datetime        # 日期時間型別
from typing import Optional          # 可選欄位（可為 None）

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
# BaseModel：Pydantic 基礎類別；ConfigDict：模型設定；EmailStr：Email 格式驗證；Field：欄位設定；field_validator：欄位級驗證


# ── 會員註冊 ──────────────────────────────────────────────
class MemberRegister(BaseModel):
    """會員註冊時的請求資料結構：驗證註冊表單送出的資料"""
    email: EmailStr                                      # 登入帳號（Email 格式自動驗證）
    password: str = Field(min_length=8, max_length=128)  # 密碼（8~128 碼）
    display_name: str = Field(min_length=1, max_length=100)  # 顯示名稱（1~100 字）
    gender: str = Field(default="", max_length=10)          # 性別（可留空，只能為 男/女/其他）
    age: str = Field(default="", max_length=10)          # 年齡
    zodiac: str = Field(default="", max_length=10)       # 星座
    occupation: str = Field(default="", max_length=100)  # 職業
    city: str = Field(default="", max_length=100)        # 居住縣市
    district: str = Field(default="", max_length=100)    # 居住區域
    interests: str = Field(default="", max_length=500)   # 興趣（逗號分隔字串，可留空）
    preferred_cuisine: str = Field(default="", max_length=500)  # 偏好料理（逗號分隔字串）
    bio: str = ""                                        # 自我介紹

    @field_validator("display_name")
    @classmethod
    def check_display_name(cls, value: str) -> str:
        """顯示名稱去除首尾空白後不可為空，避免全空白字串存入資料庫"""
        value = value.strip()
        if not value:
            raise ValueError("顯示名稱不可為空白")
        return value

    @field_validator("gender")
    @classmethod
    def check_gender(cls, value: str) -> str:
        """性別可為空白（未填寫）或「男 / 女 / 其他」其一"""
        value = value.strip()
        if value != "" and value not in ("男", "女", "其他"):
            raise ValueError("性別必須為 男/女/其他")
        return value

    @field_validator("age")
    @classmethod
    def check_age(cls, value: str) -> str:
        """年齡必須是 0~150 之間的整數（以字串儲存），空白表示未填寫"""
        if value == "":
            return value
        try:
            n = int(value)
        except (TypeError, ValueError):
            raise ValueError("年齡必須是數字")
        if not (0 <= n <= 150):
            raise ValueError("年齡必須介於 0~150")
        return str(n)

    @field_validator("interests")
    @classmethod
    def check_interests(cls, value: str) -> str:
        """興趣若有填寫，至少需勾選 3 項（與前端需求一致）"""
        items = [x.strip() for x in value.split(",") if x.strip()]
        if value.strip() and len(items) < 3:
            raise ValueError("請至少選擇 3 項興趣")
        return ",".join(items)

    @field_validator("preferred_cuisine")
    @classmethod
    def check_preferred_cuisine(cls, value: str) -> str:
        """偏好料理若有填寫，至少需勾選 3 項（與前端需求一致）"""
        items = [x.strip() for x in value.split(",") if x.strip()]
        if value.strip() and len(items) < 3:
            raise ValueError("請至少選擇 3 項偏好料理")
        return ",".join(items)


# ── 登入 ────────────────────────────────────────────────
class LoginRequest(BaseModel):
    """登入時的請求資料結構：驗證登入表單送出的帳號密碼"""
    email: EmailStr
    password: str = Field(max_length=128)   # 上限與註冊一致，避免超長密碼拖慢雜湊驗證


# ── 會員資料更新 ──────────────────────────────────────────
class MemberUpdate(BaseModel):
    """更新會員個人資料的請求資料結構（Email 與密碼不可在此修改）"""
    display_name: str = Field(min_length=1, max_length=100)
    gender: str = Field(default="", max_length=10)
    age: str = Field(default="", max_length=10)
    zodiac: str = Field(default="", max_length=10)
    occupation: str = Field(default="", max_length=100)
    city: str = Field(default="", max_length=100)
    district: str = Field(default="", max_length=100)
    interests: str = Field(default="", max_length=500)
    preferred_cuisine: str = Field(default="", max_length=500)
    bio: str = ""                                        # 自我介紹

    @field_validator("display_name")
    @classmethod
    def check_display_name(cls, value: str) -> str:
        """顯示名稱去除首尾空白後不可為空，避免全空白字串存入資料庫"""
        value = value.strip()
        if not value:
            raise ValueError("顯示名稱不可為空白")
        return value

    @field_validator("gender")
    @classmethod
    def check_gender(cls, value: str) -> str:
        """性別可為空白（未填寫）或「男 / 女 / 其他」其一"""
        value = value.strip()
        if value != "" and value not in ("男", "女", "其他"):
            raise ValueError("性別必須為 男/女/其他")
        return value

    @field_validator("age")
    @classmethod
    def check_age(cls, value: str) -> str:
        """年齡必須是 0~150 之間的整數（以字串儲存），空白表示未填寫"""
        if value == "":
            return value
        try:
            n = int(value)
        except (TypeError, ValueError):
            raise ValueError("年齡必須是數字")
        if not (0 <= n <= 150):
            raise ValueError("年齡必須介於 0~150")
        return str(n)

    @field_validator("interests")
    @classmethod
    def check_interests(cls, value: str) -> str:
        """興趣若有填寫，至少需勾選 3 項（與前端需求一致）"""
        items = [x.strip() for x in value.split(",") if x.strip()]
        if value.strip() and len(items) < 3:
            raise ValueError("請至少選擇 3 項興趣")
        return ",".join(items)

    @field_validator("preferred_cuisine")
    @classmethod
    def check_preferred_cuisine(cls, value: str) -> str:
        """偏好料理若有填寫，至少需勾選 3 項（與前端需求一致）"""
        items = [x.strip() for x in value.split(",") if x.strip()]
        if value.strip() and len(items) < 3:
            raise ValueError("請至少選擇 3 項偏好料理")
        return ",".join(items)


# ── 會員回應 ──────────────────────────────────────────────
class Member(BaseModel):
    """會員資料的 API 回應結構：回傳會員完整資料給前端"""
    model_config = ConfigDict(from_attributes=True)     # 允許直接從 ORM 物件轉換
    id: int                                              # 會員編號
    email: EmailStr
    display_name: str
    gender: str = ""
    age: str = ""
    zodiac: str = ""
    occupation: str = ""
    city: str = ""
    district: str = ""
    interests: str = ""
    preferred_cuisine: str = ""
    bio: str = ""
    created_at: datetime                                  # 註冊時間


class MemberPublic(BaseModel):
    """公開會員資料的 API 回應結構（不含 Email，供檢視他人資料時使用）"""
    model_config = ConfigDict(from_attributes=True)     # 允許直接從 ORM 物件轉換
    id: int                                              # 會員編號
    display_name: str
    gender: str = ""
    age: str = ""
    zodiac: str = ""
    occupation: str = ""
    city: str = ""
    district: str = ""
    interests: str = ""
    preferred_cuisine: str = ""
    bio: str = ""
    created_at: datetime                                  # 註冊時間


# ── 登入回應 ──────────────────────────────────────────────
class LoginResponse(BaseModel):
    """登入成功後的回應資料結構：回傳會員編號、顯示名稱與登入憑證"""
    member_id: int
    display_name: str
    token: str


# ── 活動建立 ──────────────────────────────────────────────
class ActivityCreate(BaseModel):
    """建立活動的請求資料結構：驗證發起活動表單送出的資料
    （發起人由登入身分決定，不由請求內容指定）"""
    title: str = Field(min_length=1, max_length=200)     # 活動名稱（1~200 字）
    description: str = ""                                # 活動說明（Text 無長度上限）
    category: str = Field(min_length=1, max_length=50)   # 活動分類（必填，對應 DB String(50)）
    city: str = Field(min_length=1, max_length=100)      # 活動縣市（必填，對應 DB String(100)）
    location_name: str = Field(min_length=1, max_length=200)  # 活動地點（必填，對應 DB String(200)）
    activity_date: datetime                              # 活動時間（必填）
    deadline: datetime                                   # 報名截止時間（必填）
    max_participants: int = Field(gt=0)                  # 人數上限（必須 > 0）
    image_url: str = Field(default="", max_length=500)   # 封面圖片網址（對應 DB String(500)）

    @field_validator("title", "category", "city", "location_name")
    @classmethod
    def check_required_text(cls, value: str) -> str:
        """必填文字欄位：去除首尾空白後不可為空，避免全空白字串存入資料庫"""
        value = value.strip()
        if not value:
            raise ValueError("此欄位不可為空白")
        return value

    @field_validator("image_url")
    @classmethod
    def check_image_url(cls, value: str) -> str:
        """封面圖片網址：僅允許空字串或 http/https 開頭的網址
        （同時避免前端以背景圖 url() 注入 CSS/script）"""
        value = value.strip()
        if value and not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("封面圖片網址必須以 http:// 或 https:// 開頭")
        return value


class ActivityUpdate(ActivityCreate):
    """更新活動的請求資料結構（欄位與建立相同）"""
    pass


# ── 活動回應 ──────────────────────────────────────────────
class Activity(BaseModel):
    """活動資料的 API 回應結構：回傳單一活動或活動列表給前端"""
    model_config = ConfigDict(from_attributes=True)      # 允許直接從 ORM 物件轉換
    id: int                                              # 活動編號
    organizer_id: int                                    # 發起人編號
    organizer_name: str = ""                             # 發起人顯示名稱
    title: str
    description: str
    category: str
    city: str
    location_name: str
    activity_date: datetime
    deadline: datetime
    max_participants: int
    approved_count: int = 0                              # 已核准人數
    image_url: str
    status: str
    created_at: datetime
    my_application_id: Optional[int] = None              # 我的申請編號（未申請為 None）
    my_application_status: Optional[str] = None          # 我的申請狀態（未申請為 None）


# ── 申請建立 ──────────────────────────────────────────────
class ApplicationCreate(BaseModel):
    """申請參加活動的請求資料結構：驗證申請表單送出的資料
    （申請人由登入身分決定，不由請求內容指定）"""
    message: str = ""                                    # 申請留言


# ── 申請回應 ──────────────────────────────────────────────
class Application(BaseModel):
    """申請資料的 API 回應結構：回傳一筆申請的資料給前端"""
    model_config = ConfigDict(from_attributes=True)      # 允許直接從 ORM 物件轉換
    id: int                                              # 申請編號
    activity_id: int                                     # 活動編號
    member_id: int                                       # 申請人編號
    member_name: str = ""                                # 申請人顯示名稱
    activity_title: str = ""                             # 活動名稱
    message: str
    status: str
    created_at: datetime


# ── 通知回應 ──────────────────────────────────────────────
class Notification(BaseModel):
    """通知資料的 API 回應結構：回傳一筆通知的資料給前端"""
    model_config = ConfigDict(from_attributes=True)      # 允許直接從 ORM 物件轉換
    id: int                                              # 通知編號
    member_id: int                                       # 收件人編號
    activity_id: int                                     # 相關活動編號
    activity_title: str = ""                             # 相關活動名稱
    message: str                                         # 通知內容
    is_read: int                                         # 是否已讀（0 未讀 / 1 已讀）
    created_at: datetime                                 # 通知時間


# ── 推薦回應 ──────────────────────────────────────────────
class Recommendation(Activity):
    """推薦活動的回應結構（繼承 Activity，再加上評分與推薦原因）"""
    score: int                                           # 推薦分數（分數越高越推薦）
    reasons: list[str]                                   # 推薦原因列表（供前端顯示）
