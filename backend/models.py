"""
資料庫模型定義（backend/models.py）
===================================
本模組使用 SQLAlchemy ORM 定義四張資料表：

1. members（會員資料表）
2. activities（活動資料表）
3. applications（活動申請資料表）
4. favorites（活動追蹤資料表）

並定義彼此的關聯關係：
- Member 1 ── N Activity        （一個會員可以建立多個活動）
- Member 1 ── N Application     （一個會員可以申請多個活動）
- Activity 1 ── N Application   （一個活動可以有多筆申請）
- Member 1 ── N Favorite        （一個會員可以追蹤多個活動）
- Activity 1 ── N Favorite      （一個活動可以被多個會員追蹤）
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
# Column：定義欄位；ForeignKey：外鍵；UniqueConstraint：唯一性限制
from sqlalchemy.orm import relationship               # 定義 ORM 物件之間的關聯

from .database import Base, taipei_now               # 從 database 模組取得 ORM 基礎類別與時間工具
# taipei_now：取得當前台北時間（naive datetime），作為 created_at 欄位 default 使用


class Member(Base):
    """會員資料表：儲存使用者的帳號、個人資料與興趣等資訊"""
    __tablename__ = "members"                                          # 資料表名稱

    id = Column(Integer, primary_key=True, index=True)                 # 會員編號（主鍵）
    email = Column(String(255), unique=True, nullable=False, index=True)   # 登入帳號（Email，唯一不可重複）
    password_hash = Column(String(255), nullable=False)                # 密碼雜湊值（不存明文）
    display_name = Column(String(100), nullable=False)                 # 顯示名稱（必填）
    gender = Column(String(10), default="")                            # 性別（男/女/其他）
    age = Column(String(10), default="")                               # 年齡（以字串儲存）
    zodiac = Column(String(10), default="")                            # 星座
    occupation = Column(String(100), default="")                       # 職業
    city = Column(String(100), default="")                             # 居住縣市
    district = Column(String(100), default="")                         # 居住區域
    interests = Column(String(500), default="")                        # 興趣（逗號分隔，供推薦系統使用）
    preferred_cuisine = Column(String(500), default="")                # 偏好料理（逗號分隔）
    bio = Column(Text, default="")                                     # 自我介紹
    created_at = Column(DateTime, default=taipei_now)                  # 註冊時間（預設為現在）

    # 一對多關聯：會員 → 建立的活動（透過 organizer_id 串聯）
    activities = relationship("Activity", back_populates="organizer")
    # 一對多關聯：會員 → 提出的申請（透過 member_id 串聯）
    applications = relationship("Application", back_populates="member")
    # 一對多關聯：會員 → 追蹤的活動（透過 member_id 串聯）
    favorites = relationship("Favorite", back_populates="member")


class Activity(Base):
    """活動資料表：儲存聚會活動的基本資訊與發起人"""
    __tablename__ = "activities"                                       # 資料表名稱

    id = Column(Integer, primary_key=True, index=True)                 # 活動編號（主鍵）
    organizer_id = Column(Integer, ForeignKey("members.id"), nullable=False)  # 發起人會員編號（外鍵→members.id）
    title = Column(String(200), nullable=False)                        # 活動名稱（必填）
    description = Column(Text, default="")                             # 活動說明
    category = Column(String(50), nullable=False)                      # 活動分類（美食饗宴/桌遊派對...）
    city = Column(String(100), nullable=False)                         # 活動縣市（必填）
    location_name = Column(String(200), nullable=False)                # 活動詳細地點（必填）
    activity_date = Column(DateTime, nullable=False)                   # 活動時間（必填）
    deadline = Column(DateTime, nullable=False)                        # 報名截止時間（必填）
    max_participants = Column(Integer, nullable=False)                 # 人數上限（必填）
    image_url = Column(String(500), default="")                        # 封面圖片網址
    status = Column(String(20), default="open")                        # 活動狀態（open 開放 / closed 關閉）
    created_at = Column(DateTime, default=taipei_now)                  # 建立時間（預設為現在）

    # 多對一關聯：活動 → 發起人（取得 organizer 即為會員物件）
    organizer = relationship("Member", back_populates="activities")
    # 一對多關聯：活動 → 申請（cascade 表示刪除活動時連帶刪除相關申請）
    applications = relationship("Application", back_populates="activity", cascade="all, delete-orphan")
    # 一對多關聯：活動 → 照片
    photos = relationship("ActivityPhoto", back_populates="activity", cascade="all, delete-orphan")
    # 一對多關聯：活動 → 追蹤紀錄（cascade 表示刪除活動時連帶刪除相關追蹤）
    favorites = relationship("Favorite", back_populates="activity", cascade="all, delete-orphan")


class Application(Base):
    """活動申請資料表：記錄會員報名活動的申請單與審核狀態"""
    __tablename__ = "applications"                                     # 資料表名稱
    # 唯一限制：同一會員不可重複申請同一活動（activity_id + member_id 組合唯一）
    __table_args__ = (UniqueConstraint("activity_id", "member_id", name="uq_activity_member"),)

    id = Column(Integer, primary_key=True, index=True)                 # 申請編號（主鍵）
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=False)   # 申請的活動（外鍵→activities.id）
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)        # 申請的會員（外鍵→members.id）
    message = Column(Text, default="")                                 # 申請留言（給發起人看的訊息）
    status = Column(String(20), default="pending")                     # 申請狀態（pending/approved/rejected/cancelled）
    created_at = Column(DateTime, default=taipei_now)                  # 申請時間（預設為現在）

    # 多對一關聯：申請 → 活動（取得 activity 即為活動物件）
    activity = relationship("Activity", back_populates="applications")
    # 多對一關聯：申請 → 會員（取得 member 即為會員物件）
    member = relationship("Member", back_populates="applications")


class Notification(Base):
    """通知資料表：記錄發給會員的通知（目前用於發起人收到新報名通知）"""
    __tablename__ = "notifications"                                          # 資料表名稱

    id = Column(Integer, primary_key=True, index=True)                       # 通知編號（主鍵）
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False, index=True)  # 收件人（活動發起人）
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=False)         # 相關活動
    message = Column(String(500), default="")                                # 通知內容
    is_read = Column(Integer, default=0)                                     # 是否已讀（0 未讀 / 1 已讀）
    created_at = Column(DateTime, default=taipei_now)                        # 通知時間（預設為現在）

    # 多對一關聯：通知 → 活動（取得 activity 即為活動物件，用於顯示活動名稱）
    activity = relationship("Activity")
    # 多對一關聯：通知 → 會員（取得 member 即為收件人會員物件）
    member = relationship("Member")


class ActivityPhoto(Base):
    """活動照片資料表：儲存活動的圖片與說明"""
    __tablename__ = "activity_photos"

    id = Column(Integer, primary_key=True, index=True)                       # 照片編號（主鍵）
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=False, index=True)  # 所屬活動（外鍵→activities.id）
    image_url = Column(String(500), nullable=False, default="")              # 圖片網址（必填）
    caption = Column(String(200), default="")                                # 圖片說明
    sort_order = Column(Integer, default=0)                                  # 排序（越小越前面）
    created_at = Column(DateTime, default=taipei_now)                        # 建立時間（預設為現在）

    # 多對一關聯：照片 → 活動（取得 activity 即為活動物件）
    activity = relationship("Activity", back_populates="photos")


class Favorite(Base):
    """活動追蹤資料表：記錄會員追蹤的活動（愛心收藏）"""
    __tablename__ = "favorites"
    # 唯一限制：同一會員不可重複追蹤同一活動（activity_id + member_id 組合唯一）
    __table_args__ = (UniqueConstraint("activity_id", "member_id", name="uq_favorite_activity_member"),)

    id = Column(Integer, primary_key=True, index=True)                 # 追蹤編號（主鍵）
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=False, index=True)  # 追蹤的活動（外鍵→activities.id）
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False, index=True)        # 追蹤的會員（外鍵→members.id）
    created_at = Column(DateTime, default=taipei_now)                  # 追蹤時間（預設為現在）

    # 多對一關聯：追蹤 → 活動（取得 activity 即為活動物件）
    activity = relationship("Activity", back_populates="favorites")
    # 多對一關聯：追蹤 → 會員（取得 member 即為會員物件）
    member = relationship("Member", back_populates="favorites")



