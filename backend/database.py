"""
資料庫連線設定（backend/database.py）
======================================
支援 MSSQL（原始設計）、PostgreSQL / Supabase、SQLite 三種引擎。

引擎由 DB_TYPE 環境變數決定：
- postgres / supabase → postgresql+psycopg2（需安裝 psycopg2-binary，連 Supabase 強制 SSL）
- mssql              → mssql+pyodbc（需安裝 pyodbc 與 ODBC Driver）
- sqlite / 其他       → 直接使用 DATABASE_URL（預設 sqlite:///./jiu_eat.db）

本模組提供：
- taipei_now()   ：取得當前台北時間（naive datetime）
- to_naive_taipei()：將 timezone-aware datetime 轉為台北時區 naive datetime
- engine         ：SQLAlchemy 引擎（實際連線的物件）
- SessionLocal   ：產生資料庫 Session 的工廠
- Base           ：所有 ORM 模型的共同基礎類別
- get_db()       ：FastAPI 依賴注入用的 Session 供應器
"""

import os          # 讀取環境變數
from datetime import datetime, timedelta, timezone   # 日期時間與時區處理

from sqlalchemy import URL, create_engine     # 建立資料庫引擎（URL.create 可正確處理密碼特殊字元）
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


# 引擎型別：postgres / supabase / mssql / sqlite
DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()

if DB_TYPE in ("postgres", "supabase"):
    # PostgreSQL / Supabase：DB_HOST 範例 db.<project-ref>.supabase.co
    # Supabase 強制 SSL，預設 sslmode=require
    DATABASE_URL = URL.create(
        drivername="postgresql+psycopg2",
        username=os.getenv("DB_USERNAME", "postgres"),
        password=os.environ["DB_PASSWORD"],
        host=os.environ["DB_HOST"],
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "postgres"),
        query={"sslmode": os.getenv("DB_SSLMODE", "require")},
    )
    connect_args = {}
elif DB_TYPE == "mssql":
    # Microsoft SQL Server：備援方案（需另裝 ODBC Driver）
    DATABASE_URL = URL.create(
        drivername="mssql+pyodbc",
        username=os.environ["DB_USERNAME"],
        password=os.environ["DB_PASSWORD"],
        host=os.environ["DB_HOST"],
        port=int(os.getenv("DB_PORT", "1433")),
        database=os.environ["DB_NAME"],
        query={
            "driver": os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server"),
            "TrustServerCertificate": os.getenv("DB_TRUST_SERVER_CERTIFICATE", "yes"),
        },
    )
    connect_args = {}
else:
    # SQLite：可透過 DATABASE_URL 完全覆寫（例如 sqlite:///./jiu_eat.db）
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jiu_eat.db")
    # SQLite 需要 check_same_thread=False（允許跨執行緒存取），其他資料庫不需要
    connect_args = {"check_same_thread": False}

# 建立資料庫引擎：管理實際的資料庫連線池與方言（dialect）
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)

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