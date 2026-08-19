# Jiu-Eat：本地資料庫建置完整指南（含 Supabase）

## 1. 文件目的

本文件說明如何把 `DB_csv/` 下的 CSV 資料建立成「本地資料庫」，並提供兩種主流做法：

- **方案 A：Supabase（雲端 PostgreSQL，建議）**
  - 免安裝、免費、7x24 運作，不受本機 Docker 開機限制
  - 適合展示、測試、開發共用
- **方案 B：MSSQL via Docker Compose（專案原始設計）**
  - 與 `docker-compose.yml` 一致，資料在本機 volume

目前專案技術棧：

```text
FastAPI → SQLAlchemy → 資料庫（MSSQL / SQLite / PostgreSQL 皆可）
```

SQLAlchemy 已將資料庫差異抽象化，因此切換引擎**不需要改 API 路由、models 與前端**，
只需調整連線設定與安裝對應驅動。

---

## 2. 現況盤點：CSV 與資料表對應

### 2.1 主程式 4 張資料表（`backend/models.py`）

| CSV 檔案 | 資料表 | 資料筆數（不含表頭） | 與 Model 對應 |
| --- | --- | --- | --- |
| `members.csv` | `members` | 32 | ✅ `Member` |
| `activities.csv` | `activities` | 20 | ✅ `Activity` |
| `applications.csv` | `applications` | 34 | ✅ `Application` |
| `notifications.csv` | `notifications` | 21 | ✅ `Notification` |
| `activity_photos.csv` | `activity_photos` | 0（只有表頭） | ❌ **尚未定義 Model** |

### 2.2 外鍵依賴（匯入順序依據）

```text
members（無外鍵）
  └─ activities（organizer_id → members.id）
       └─ applications（activity_id → activities.id, member_id → members.id）
       └─ notifications（activity_id → activities.id, member_id → members.id）
       └─ activity_photos（activity_id → activities.id）   ※ 需先補 Model
```

**匯入順序必須為：`members → activities → applications → notifications → activity_photos`。**

### 2.3 特殊檔案

| 檔案 | 說明 |
| --- | --- |
| `members_fake.csv` | 2000 筆「假會員」資料，供 `ml/train.py`（FP-Growth）訓練推薦規則用。**主程式不需要這張表**，推薦規則已內建於 `backend/services/recommendation_service.py` 的 `FP_RULES`。若想重新訓練推薦，才需要匯入。 |

---

## 3. 整體流程總覽

```text
[1] 決定資料庫引擎（Supabase / MSSQL / SQLite）
        ↓
[2] 建立資料庫與取得連線資訊（Supabase 專案建置）
        ↓
[3] 安裝 Python 資料庫驅動（psycopg2 或 pyodbc）
        ↓
[4] 設定連線（DATABASE_URL 或 DB_* 環境變數）
        ↓
[5] 建立資料表（FastAPI create_all 自動建立 或 手動 SQL）
        ↓
[6] 匯入 CSV（scripts/import_csv.py，依外鍵順序）
        ↓
[7] 修正 Postgres 序號（setval），避免之後新增資料主鍵衝突
        ↓
[8] 啟動 FastAPI 並驗證
```

---

## 4. 資料庫引擎選擇

| 項目 | Supabase（PostgreSQL） | MSSQL via Docker | SQLite |
| --- | --- | --- | --- |
| 安裝成本 | 無（雲端） | 需 Docker Desktop | 無 |
| 常駐時間 | 雲端 7x24 | 需本機容器開啟 | 本機檔案 |
| 免費額度 | 免費方案（500MB DB） | Docker 免費 | 免費 |
| 與專案相容性 | 需改連線 + 加 psycopg2 | 原廠設定 | 已支援（README 明載） |
| 適合場景 | **展示 / 測試 / 多人共用** | 本機開發（沿用原始設計） | 快速原型 |
| 閒置暫停 | 免費專案閒置約 7 天會暫停（可恢復） | 無 | 無 |

> **建議：若沒有特別理由，採用方案 A（Supabase）。** 本文件後續以方案 A 為主線，
> 方案 B 僅列出差異步驟（見第 11 節）。

---

## 5. 方案 A：Supabase 完整建置資料庫

### 5.1 建立專案

1. 前往 <https://supabase.com> 註冊／登入（可用 GitHub 帳號）。
2. 點 **New project**。
3. 依序填寫：
   - **Organization**：選取或新建一個組織（例如 `jiu-eat`）。
   - **Project name**：輸入 `jiu-eat`。
   - **Database Password**：設定資料庫密碼，**務必記下並妥善保存**（之後連線需要）。
   - **Region**：選擇 **Southeast Asia (Singapore)** 或離你最近的機房（降低延遲）。
   - **Pricing Plan**：選 **Free**。
4. 點 **Create new project**，等待約 1~2 分鐘完成佈建。

### 5.2 取得連線資訊

進入 **Project Settings → Database → Connection string**，會看到兩種連線方式：

| 方式 | Host | Port | 用途 |
| --- | --- | --- | --- |
| **Direct connection** | `db.<project-ref>.supabase.co` | 5432 | 單一應用程式使用，較簡單 |
| **Pooler（Transaction mode）** | `aws-0-ap-southeast-1.pooler.supabase.com` | 6543 | 多連線併發、Serverless 建議 |

SQLAlchemy 連線建議用 **Direct connection**（開發環境單純）：

```text
postgresql://postgres.<project-ref>:YOUR_PASSWORD@db.<project-ref>.supabase.co:5432/postgres
```

> - 使用者名稱固定是 `postgres.<project-ref>`（或 `postgres`，依 Dashboard 顯示）。
> - 若密碼含 `@ : / # %` 等 URL 特殊字元，**務必做 URL encoding**。
>   建議直接用第 6.2 節的 `URL.create()` 寫法，可完全避開此問題。
> - 若忘了密碼：**Project Settings → Database → Reset database password** 重設。

### 5.3 建立資料表（二選一）

#### 方式 1（推薦）：由 FastAPI `create_all` 自動建立

FastAPI 啟動時會執行 `models.Base.metadata.create_all(bind=engine)`，
只要連線設定正確，第一次啟動就會自動建立 4 張表。見第 8 節。

> 注意：`activity_photos` 因尚未定義 Model，不會被自動建立。如需此表，先完成第 7.1 節。

#### 方式 2：用 Supabase SQL Editor 手動建立

1. Dashboard 左側選 **SQL Editor → New query**。
2. 貼上下列 DDL 並執行：

```sql
CREATE TABLE members (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    gender VARCHAR(10) DEFAULT '',
    age VARCHAR(10) DEFAULT '',
    zodiac VARCHAR(10) DEFAULT '',
    occupation VARCHAR(100) DEFAULT '',
    city VARCHAR(100) DEFAULT '',
    district VARCHAR(100) DEFAULT '',
    interests VARCHAR(500) DEFAULT '',
    preferred_cuisine VARCHAR(500) DEFAULT '',
    bio TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX ix_members_id ON members (id);
CREATE INDEX ix_members_email ON members (email);

CREATE TABLE activities (
    id SERIAL PRIMARY KEY,
    organizer_id INTEGER NOT NULL REFERENCES members(id),
    title VARCHAR(200) NOT NULL,
    description TEXT DEFAULT '',
    category VARCHAR(50) NOT NULL,
    city VARCHAR(100) NOT NULL,
    location_name VARCHAR(200) NOT NULL,
    activity_date TIMESTAMP NOT NULL,
    deadline TIMESTAMP NOT NULL,
    max_participants INTEGER NOT NULL,
    image_url VARCHAR(500) DEFAULT '',
    status VARCHAR(20) DEFAULT 'open',
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX ix_activities_id ON activities (id);

CREATE TABLE applications (
    id SERIAL PRIMARY KEY,
    activity_id INTEGER NOT NULL REFERENCES activities(id),
    member_id INTEGER NOT NULL REFERENCES members(id),
    message TEXT DEFAULT '',
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_activity_member UNIQUE (activity_id, member_id)
);
CREATE INDEX ix_applications_id ON applications (id);

CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    member_id INTEGER NOT NULL REFERENCES members(id),
    activity_id INTEGER NOT NULL REFERENCES activities(id),
    message VARCHAR(500) DEFAULT '',
    is_read INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX ix_notifications_id ON notifications (id);
CREATE INDEX ix_notifications_member_id ON notifications (member_id);

-- activity_photos（需先補 Model，見 7.1；或直接建表）
CREATE TABLE activity_photos (
    id SERIAL PRIMARY KEY,
    activity_id INTEGER NOT NULL REFERENCES activities(id),
    image_url VARCHAR(500) NOT NULL DEFAULT '',
    caption VARCHAR(200) DEFAULT '',
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX ix_activity_photos_id ON activity_photos (id);
CREATE INDEX ix_activity_photos_activity_id ON activity_photos (activity_id);
```

> 直接手動建表時，請改用 `TIMESTAMP`／`SERIAL`，不要沿用 MSSQL 的 `DATETIME`／`IDENTITY` 寫法。

---

## 6. 修改後端連線設定

### 6.1 安裝 PostgreSQL 驅動

目前專案使用 `pyodbc`（MSSQL）。要連 Supabase 需改為 `psycopg2`。

```bash
uv add "psycopg2-binary>=2.9"
uv sync
```

若部署環境只用 `requirements.txt`，也請補上：

```text
psycopg2-binary>=2.9
```

### 6.2 修改 `backend/database.py`

現有 `database.py` 的 `ensure_database_exists()` 只對 `mssql` 開頭的連線字串動作，
連 Postgres 時會直接略過（安全），但連線字串的建構邏輯仍是 MSSQL 導向。
建議改成支援多種引擎的版本：

```python
"""
資料庫連線設定（backend/database.py）
======================================
支援 MSSQL（原設計）、PostgreSQL（Supabase）、SQLite（本機）三種引擎。
連線方式由 DB_TYPE 環境變數決定：
- postgres / supabase → postgresql+psycopg2（需安裝 psycopg2-binary）
- mssql              → mssql+pyodbc（需安裝 pyodbc 與 ODBC Driver）
- sqlite / 其他       → 直接使用 DATABASE_URL
"""

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# 台北時區（UTC+8）
tz_taipei = timezone(timedelta(hours=8), "Asia/Taipei")


def taipei_now():
    return datetime.now(tz_taipei).replace(tzinfo=None)


def to_naive_taipei(dt):
    if isinstance(dt, datetime) and dt.tzinfo is not None:
        return dt.astimezone(tz_taipei).replace(tzinfo=None)
    return dt


DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()

if DB_TYPE in ("postgres", "supabase"):
    # Supabase / PostgreSQL：DB_HOST 範例 db.abc.supabase.co
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
    # SQLite（本機快速開發）
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jiu_eat.db")
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

> 此版本保留 `taipei_now`／`to_naive_taipei`（`backend/common.py` 會用到），
> 並刪除 MSSQL 專屬的 `ensure_database_exists()`（Supabase／SQLite 都「已存在資料庫」，不需要建庫）。

### 6.3 設定環境變數

macOS / Linux Bash：

```bash
export DB_TYPE='postgres'
export DB_HOST='db.你的專案ref.supabase.co'
export DB_PORT='5432'
export DB_NAME='postgres'
export DB_USERNAME='postgres'
export DB_PASSWORD='你的資料庫密碼'
```

Windows PowerShell：

```powershell
$env:DB_TYPE = 'postgres'
$env:DB_HOST = 'db.你的專案ref.supabase.co'
$env:DB_PORT = '5432'
$env:DB_NAME = 'postgres'
$env:DB_USERNAME = 'postgres'
$env:DB_PASSWORD = '你的資料庫密碼'
```

> 密碼請透過環境變數注入，**不要寫進 Git**。

### 6.4 連線測試

```bash
uv run python -c "from backend.database import engine; c = engine.connect(); print('PostgreSQL connection OK'); c.close()"
```

---

## 7. 補齊 `activity_photos` Model（可選）

`activity_photos.csv` 目前只有表頭、沒有資料，且 `models.py` 未定義此表。
若要保留未來擴充照片功能，在 `backend/models.py` 加入：

```python
class ActivityPhoto(Base):
    """活動照片資料表：儲存活動的圖片與說明"""
    __tablename__ = "activity_photos"

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=False)
    image_url = Column(String(500), nullable=False, default="")
    caption = Column(String(200), default="")
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=taipei_now)

    activity = relationship("Activity", backref="photos")
```

加入後，`create_all` 會自動建立 `activity_photos` 表。

---

## 8. 建立資料表（自動）

執行下列指令讓 FastAPI 啟動時自動建表：

```bash
uv run python -c "from backend.main import app; from backend import models; from backend.database import engine; models.Base.metadata.create_all(bind=engine); print('Tables created')"
```

> 或直接啟動伺服器（啟動時會自動 `create_all`，見 `backend/main.py:24`）。

---

## 9. 匯入 CSV 資料

### 9.1 建立匯入腳本 `scripts/import_csv.py`

```python
"""
CSV 匯入腳本（scripts/import_csv.py）
=====================================
將 DB_csv/*.csv 依外鍵順序匯入資料庫。

用法：
    uv run python scripts/import_csv.py            # 正常匯入（略過已存在的主鍵）
    uv run python scripts/import_csv.py --reset    # 先清空資料表再匯入

注意：
- 保留 CSV 內原有 id，避免破壞外鍵關聯。
- Postgres（Supabase）匯入後會自動 setval 修正序號，
  否則之後用 API 新增資料會主鍵衝突。
- members_fake.csv 為 ML 訓練用假資料，預設不匯入；
  需要時可用 --with-fake 開啟（僅在資料表已存在的狀況下）。
"""

import argparse
import csv
import os
from datetime import datetime

from sqlalchemy import text

from backend.database import SessionLocal, engine

CSV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "DB_csv")

# 依外鍵依賴順序定義：檔案 → 資料表
TABLES = [
    ("members.csv", "members"),
    ("activities.csv", "activities"),
    ("applications.csv", "applications"),
    ("notifications.csv", "notifications"),
    ("activity_photos.csv", "activity_photos"),
]

FALLBACK_TIME = "%Y-%m-%d %H:%M:%S"


def parse_time(value):
    """解析 CSV 時間欄位（可能含或不含微秒）"""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        return datetime.strptime(value, FALLBACK_TIME)


def clean(row):
    """把空字串轉成 None，時間欄位轉成 datetime"""
    out = {}
    for k, v in row.items():
        v = v.strip()
        if v == "":
            out[k] = None
        elif k.endswith("_at") or k in ("activity_date", "deadline"):
            out[k] = parse_time(v)
        else:
            out[k] = v
    return out


def reset(db):
    """依外鍵順序清空資料表（子表先刪）"""
    print("清空資料表...")
    for _, table in reversed(TABLES):
        db.execute(text(f"DELETE FROM {table}"))
    db.commit()


def fix_sequences(db):
    """修正 Postgres 序列，避免之後新增資料主鍵衝突"""
    for _, table in TABLES:
        try:
            db.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"(SELECT COALESCE(MAX(id), 1) FROM {table}))"
            ))
            print(f"  ✓ 已修正 {table} 的序列")
        except Exception:
            print(f"  - 略過 {table}（非 Postgres 或無序列）")


def import_csv(db):
    for filename, table in TABLES:
        path = os.path.join(CSV_DIR, filename)
        if not os.path.exists(path):
            print(f"  - 找不到 {filename}，略過")
            continue
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                data = clean(row)
                if data.get("id") is None:
                    continue
                exists = db.execute(
                    text(f"SELECT 1 FROM {table} WHERE id = :id"), {"id": int(data["id"])}
                ).first()
                if exists:
                    print(f"  - {table} id={data['id']} 已存在，略過")
                    continue
                cols = ", ".join(data.keys())
                placeholders = ", ".join(f":{k}" for k in data.keys())
                db.execute(
                    text(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"),
                    {k: (int(v) if k == "id" else v) for k, v in data.items()},
                )
                count += 1
            db.commit()
            print(f"  ✓ {filename} → {table}：匯入 {count} 筆")
    fix_sequences(db)


def main():
    parser = argparse.ArgumentParser(description="匯入 DB_csv 到資料庫")
    parser.add_argument("--reset", action="store_true", help="先清空資料表再匯入")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.reset:
            reset(db)
        import_csv(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

### 9.2 執行匯入

```bash
# 第一次匯入
uv run python scripts/import_csv.py

# 需要重來時
uv run python scripts/import_csv.py --reset
```

> 腳本會自動：
> 1. 依外鍵順序匯入（members → activities → applications → notifications → activity_photos）
> 2. 保留 CSV 原 id
> 3. 重複執行時略過已存在的主鍵（冪等）
> 4. Postgres 自動 `setval` 修正序號（重要！）

---

## 10. 啟動與驗證

```bash
uv run uvicorn backend.main:app --reload
```

驗證清單：

| 檢查項目 | 指令／位置 | 預期結果 |
| --- | --- | --- |
| 健康檢查 | `http://127.0.0.1:8000/api/health` | `{"status":"ok"}` |
| API 文件 | `http://127.0.0.1:8000/docs` | 正常顯示 |
| 會員數 | Supabase Table Editor → members | 32 筆 |
| 活動數 | Supabase Table Editor → activities | 20 筆 |
| 申請數 | Supabase Table Editor → applications | 34 筆 |
| 通知數 | Supabase Table Editor → notifications | 21 筆 |
| 登入測試 | `POST /api/login`（`jiaming1014@gmail.com`） | 回傳 token 與 member_id |

登入測試範例：

```bash
curl -X POST http://127.0.0.1:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"email": "jiaming1014@gmail.com", "password": "你的測試密碼"}'
```

> 密碼已雜湊，CSV 中無法得知明文；建議用 `/api/register` 建立一筆新帳號來測試。

---

## 11. 方案 B：MSSQL via Docker（原始設計）

若改用原設計的 MSSQL，只差在第 5 節的建庫方式，其餘步驟相同：

1. 安裝 Microsoft ODBC Driver 18 for SQL Server（本機）。
2. 修改連線相關設定：

```bash
export DB_TYPE='mssql'
export DB_HOST='localhost'
export DB_PORT='1433'
export DB_NAME='jiu_eat_1.2'
export DB_USERNAME='sa'
export DB_PASSWORD='Aa123456'
```

3. 啟動 MSSQL（資料保留在 volume）：

```bash
docker compose up -d db
```

> 注意：`docker-compose.yml` 中的 backend service 預設會一併啟動。
> 若只想用本機跑 backend，可只啟動 db：`docker compose up -d db`。

4. 沿用第 6.2 節的 `database.py`（`DB_TYPE=mssql`）即可，`ensure_database_exists()` 會自動建立 `jiu_eat_1.2` 資料庫。
5. 匯入與驗證步驟同第 9、10 節。

> MSSQL 用 `IDENTITY`，匯入時保留 id 不需修序列（但 `fix_sequences()` 會自動略過）。

---

## 12. 成員假資料 `members_fake`（ML 用，可選）

`members_fake.csv`（2000 筆）是 FP-Growth 訓練用假資料，欄位為會員特徵的 0/1 矩陣：
- 40 個興趣欄位、6 個居住縣市欄位、5 個活動分類欄位
- `ml/train.py` 會從資料庫的 `members_fake` 表讀取並產生 `FP_RULES`（已內建在 `recommendation_service.py`）

一般情況下**不需要匯入**。若要重新訓練推薦規則：

1. 先在資料庫建立 `members_fake` 表（欄位與 CSV 表頭一致，全部為 0/1 的 `INTEGER` 或 `BOOLEAN`，第一欄 `會員編號` 為主鍵）。
2. 用 Supabase Dashboard 的 **Table Editor → Import data from CSV** 直接匯入該檔。
3. 調整 `ml/train.py` 的連線字串為 Supabase（目前寫死 MSSQL），再執行 `python ml/train.py` 重新產生規則。

---

## 13. 常見問題

### 連不上 Supabase

```text
connection failed: sslmode value "require" invalid
```

- 確認 `DB_HOST`／`DB_PORT`／`DB_NAME` 與 Dashboard 的 Connection string 一致。
- 確認密碼正確（可在 Settings → Database 重設）。
- Supabase 強制 SSL，務必帶 `sslmode=require`（本指南已內建）。

### 匯入後新增資料主鍵衝突

```text
duplicate key value violates unique constraint "members_pkey"
```

- 原因：直接指定 id 匯入，Postgres 的 `SERIAL` 序號沒有跟著前進。
- 解決：執行 `uv run python scripts/import_csv.py` 已內建 `fix_sequences()`；
  或手動執行
  ```sql
  SELECT setval(pg_get_serial_sequence('members', 'id'), (SELECT MAX(id) FROM members));
  ```

### ModuleNotFoundError: psycopg2

```bash
uv add "psycopg2-binary>=2.9" && uv sync
```

### 時間格式解析錯誤

- CSV 有 `2026-07-28 11:17:32.370000`（含微秒）與 `2026-08-23 20:15:00`（無微秒）兩種格式，
  腳本已用 `%Y-%m-%d %H:%M:%S.%f` → `%Y-%m-%d %H:%M:%S` 雙重解析。

### 免費專案被暫停

- Supabase 免費專案閒置約 7 天會進入 Pause 狀態，連線會失敗。
- 到 Dashboard 按 **Restore** 即可恢復，資料不會遺失。

---

## 14. 檢查清單

- [ ] 已決定資料庫引擎（本指南建議 Supabase）
- [ ] Supabase 專案已建立，並取得 Connection string
- [ ] 資料庫密碼已設定且未寫入 Git
- [ ] `psycopg2-binary` 已加入相依並完成 `uv sync`
- [ ] `backend/database.py` 已改為多引擎版本
- [ ] 環境變數 `DB_TYPE / DB_HOST / DB_PORT / DB_NAME / DB_USERNAME / DB_PASSWORD` 已設定
- [ ] Python 連線測試成功（第 6.4 節）
- [ ] 資料表已建立（`create_all` 或手動 SQL，含 `activity_photos`）
- [ ] CSV 已依外鍵順序匯入（members → activities → applications → notifications → activity_photos）
- [ ] Postgres 序列已修正（`fix_sequences`）
- [ ] FastAPI 可啟動，`/api/health` 與 `/docs` 正常
- [ ] 各表筆數與 CSV 相符（32 / 20 / 34 / 21）
- [ ] 登入／註冊 CRUD 測試通過
- [ ] （選）`members_fake` 是否匯入已決定