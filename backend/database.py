"""
資料庫連線設定（backend/database.py）
======================================
本模組負責建立與資料庫的連線，並提供：
- DATABASE_URL ：資料庫連線字串（可透過環境變數覆寫）
- engine       ：SQLAlchemy 引擎（實際連線的物件）
- SessionLocal ：產生資料庫 Session 的工廠
- Base         ：所有 ORM 模型的共同基礎類別
- get_db()     ：FastAPI 依賴注入用的 Session 供應器
"""

import os          # 讀取環境變數
from datetime import datetime, timedelta, timezone   # 日期時間與時區處理

from sqlalchemy import create_engine     # 建立資料庫引擎
from sqlalchemy.orm import declarative_base, sessionmaker          # ORM 基礎類別與 Session 工廠

# 台北時區（UTC+8）：全系統時間統一以台北時間為準
tz_taipei = timezone(timedelta(hours=8), "Asia/Taipei")


def taipei_now():
    """
    取得當前台北時間（naive datetime）
    - 使用 tz_taipei 時區取得現在時間
    - 移除 tzinfo，讓存入資料庫時不會有時區落差
    """
    return datetime.now(tz_taipei).replace(tzinfo=None)


def to_naive_taipei(dt):
    """
    將 timezone-aware datetime 轉換為台北時區的 naive datetime
    - 若原本是 naive datetime，直接原樣回傳
    """
    if isinstance(dt, datetime) and dt.tzinfo is not None:
        return dt.astimezone(tz_taipei).replace(tzinfo=None)
    return dt

# 從環境變數讀取資料庫連線字串，預設為 MSSQL（Windows 整合驗證）
# 若環境變數沒有設定，則使用本機的 SQL Server + ODBC Driver 17 連線
DATABASE_URL = os.getenv("DATABASE_URL", "mssql+pyodbc://@localhost:1433/jiu_eat_1.2?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes")

# SQLite 需要 check_same_thread=False（允許跨執行緒存取），其他資料庫不需要
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# 建立資料庫引擎：管理實際的資料庫連線池與方言（dialect）
engine = create_engine(DATABASE_URL, connect_args=connect_args)

# 建立 Session 工廠
# - autocommit=False：交易不會自動提交，需手動 commit
# - autoflush=False ：查詢前不會自動 flush 未保存的變更
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ORM 模型的基礎類別：所有資料表模型（如 Member、Activity）皆繼承自此類別
Base = declarative_base()


def get_db():
    """
    FastAPI 依賴注入用：提供資料庫 Session，請求結束後自動關閉
    - 每個 HTTP 請求會建立一個新的 Session
    - 使用 yield 將 Session 交給路由函式使用
    - 請求結束後（finally）自動關閉 Session，確保連線釋放
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
