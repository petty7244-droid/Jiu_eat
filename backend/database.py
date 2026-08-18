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

# 從環境變數讀取 MSSQL 連線參數（Docker Compose 會注入這些變數）
MSSQL_SERVER = os.getenv("MSSQL_SERVER", "localhost")          # 主機（Docker 內為 db）
MSSQL_PORT = os.getenv("MSSQL_PORT", "1433")                    # 連接埠
MSSQL_DATABASE = os.getenv("MSSQL_DATABASE", "jiu_eat_1.2")     # 資料庫名稱
MSSQL_USER = os.getenv("MSSQL_USER", "sa")                      # 帳號
MSSQL_PASSWORD = os.getenv("MSSQL_SA_PASSWORD", "")             # 密碼
MSSQL_DRIVER = os.getenv("MSSQL_DRIVER", "ODBC Driver 18 for SQL Server")  # ODBC 驅動

# 組出連線字串（可透過 DATABASE_URL 直接覆寫整個連線字串）
if MSSQL_PASSWORD:
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        f"mssql+pyodbc://{MSSQL_USER}:{MSSQL_PASSWORD}@{MSSQL_SERVER}:{MSSQL_PORT}/{MSSQL_DATABASE}"
        f"?driver={MSSQL_DRIVER.replace(' ', '+')}&TrustServerCertificate=yes",
    )
else:
    # 未提供密碼時，退回本機 Windows 整合驗證（trusted_connection）
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        f"mssql+pyodbc://@{MSSQL_SERVER}:{MSSQL_PORT}/{MSSQL_DATABASE}"
        f"?driver={MSSQL_DRIVER.replace(' ', '+')}&trusted_connection=yes",
    )


def ensure_database_exists():
    """
    若目標資料庫不存在，先連到 master 建立它，再回原本資料庫。
    create_all 只會建「資料表」，不會建「資料庫」本身，因此在啟動前需自行確認資料庫存在。
    """
    if not DATABASE_URL.startswith("mssql"):
        return
    engine_master = create_engine(
        DATABASE_URL.rsplit("/", 1)[0] + "/master"
        + (DATABASE_URL.split("?", 1)[1] and "?" + DATABASE_URL.split("?", 1)[1] or ""),
        connect_args=connect_args,
    )
    try:
        with engine_master.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.exec_driver_sql(f"IF DB_ID(N'{MSSQL_DATABASE}') IS NULL CREATE DATABASE [{MSSQL_DATABASE}]")
    except Exception:
        # 建庫失敗不阻礙啟動（例如權限不足），後續連線時仍會回報真正的錯誤
        pass
    finally:
        engine_master.dispose()


# SQLite 需要 check_same_thread=False（允許跨執行緒存取），其他資料庫不需要
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# 啟動前先確保資料庫存在
ensure_database_exists()

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
