# Jiu-Eat：SQLite 切換至 Microsoft SQL Server 說明

## 1. 文件目的

目前 Jiu-Eat 使用 SQLite：

```text
FastAPI → SQLAlchemy → SQLite（jiu_eat.db）
```

本文件說明如何將資料庫改為 Microsoft SQL Server（MSSQL）：

```text
FastAPI → SQLAlchemy → pyodbc → Microsoft SQL Server
```

本專案使用 SQLAlchemy，因此主要只需調整資料庫驅動、套件與連線設定。以下功能通常不需修改：

- `backend/routers/`
- `backend/services/`
- `backend/models.py`
- `backend/schemas.py`
- `frontend/`

> 本次是切換資料庫連線，不包含將原 SQLite 資料自動搬移至 MSSQL。

## 2. 需要修改的位置

| 項目 | 檔案或環境 | 必要性 |
| --- | --- | --- |
| 安裝 Microsoft ODBC Driver | 執行主機 | 必要 |
| 加入 Python MSSQL 驅動 | `pyproject.toml`、`uv.lock` | 必要 |
| 設定連線資訊 | `DATABASE_URL` 環境變數 | 必要 |
| 建立空資料庫 | MSSQL Server | 必要 |
| 調整 `database.py` | `backend/database.py` | 現有版本通常不用改 |
| 建立正式 migration | Alembic 或 SQL Script | 正式環境建議 |

## 3. 安裝 Microsoft ODBC Driver

應用程式執行主機必須安裝 Microsoft ODBC Driver 17 for SQL Server。

### Windows 檢查方式

在「ODBC 資料來源（64 位元）」的「驅動程式」頁籤確認存在：

```text
ODBC Driver 17 for SQL Server
```

### macOS / Linux 檢查方式

```bash
odbcinst -q -d
```

應可看到：

```text
[ODBC Driver 17 for SQL Server]
```

若未安裝，請由 Microsoft 官方文件依作業系統安裝 Driver 17。

## 4. 加入 Python 套件

在專案根目錄執行：

```bash
uv add pyodbc
```

執行後，`pyproject.toml` 的 dependencies 應包含：

```toml
dependencies = [
  "fastapi>=0.115",
  "pydantic[email]>=2.0",
  "sqlalchemy>=2.0",
  "uvicorn[standard]>=0.30",
  "pyodbc>=5.0",
]
```

如果部署環境使用 `requirements.txt`，也要加入：

```text
pyodbc>=5.0
```

然後同步套件：

```bash
uv sync
```

## 5. 建立 MSSQL Database

SQLAlchemy 的 `create_all()` 可以建立資料表，但不會建立 Database。請先由 DBA 或具權限帳號執行：

```sql
CREATE DATABASE jiu_eat_1.2;
GO
```

如果 Database 已由 DBA 建立，請使用 DBA 提供的實際名稱，並確認應用程式帳號至少具有連線及資料表操作所需權限。

正式環境不建議讓應用程式帳號擁有建立 Database 等過大權限。

## 6. 設定 MSSQL 連線

目前的 `backend/database.py` 已使用 `DATABASE_URL`，並預設本機 MSSQL（`localhost:1433/jiu_eat_1.2`、ODBC Driver 17、Windows 整合驗證）：

```python
DATABASE_URL = os.getenv("DATABASE_URL",
    "mssql+pyodbc://@localhost:1433/jiu_eat_1.2?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes")
```

因此不要把真實帳號、密碼直接寫入 Git 中的 Python 程式，應由執行環境提供 `DATABASE_URL`。

### 方式 A：SQL Server 帳號密碼

連線字串格式：

```text
mssql+pyodbc://帳號:密碼@主機:1433/資料庫?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
```

macOS / Linux Bash 範例：

```bash
export DATABASE_URL='mssql+pyodbc://jiueat_app:Password@db-server:1433/jiu_eat_1.2?driver=ODBC+Driver+17+for+SQL+Server&TrustServerCertificate=yes'
```

Windows PowerShell 範例：

```powershell
$env:DATABASE_URL = 'mssql+pyodbc://jiueat_app:Password@db-server:1433/jiu_eat_1.2?driver=ODBC+Driver+17+for+SQL+Server&TrustServerCertificate=yes'
```

密碼若包含 `@`、`:`、`/`、`#`、`%` 等 URL 特殊字元，必須先做 URL encoding。為避免此問題，可採用本文件第 7 節的 `URL.create()` 寫法。

### 方式 B：Windows 整合驗證

若應用程式和 SQL Server 位於公司 Windows／網域環境，而且 DBA 指定使用 Windows 驗證，可使用 ODBC connection string：

```powershell
$env:DATABASE_URL = 'mssql+pyodbc:///?odbc_connect=DRIVER%3DODBC%20Driver%2017%20for%20SQL%20Server%3BSERVER%3Ddb-server%3BDATABASE%3Djiu_eat_1.2%3BTrusted_Connection%3Dyes%3BTrustServerCertificate%3Dyes'
```

Windows 驗證能否使用，取決於服務執行帳號、網域和 SQL Server 權限，需由 DBA 或系統管理者確認。

### 憑證設定

`TrustServerCertificate=yes` 適合本機或測試環境。正式環境應優先安裝受信任的 SQL Server 憑證，並依公司的資安規範改為驗證憑證，不應把略過憑證驗證當作固定正式設定。

## 7. 建議版 `database.py`（避免特殊字元問題）

如果要使用分開的環境變數，建議將 `backend/database.py` 改成以下形式。`URL.create()` 會正確處理密碼內的特殊字元：

```python
import os

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()

if DB_TYPE == "mssql":
    DATABASE_URL = URL.create(
        drivername="mssql+pyodbc",
        username=os.environ["DB_USERNAME"],
        password=os.environ["DB_PASSWORD"],
        host=os.environ["DB_HOST"],
        port=int(os.getenv("DB_PORT", "1433")),
        database=os.environ["DB_NAME"],
        query={
            "driver": os.getenv(
                "DB_DRIVER",
                "ODBC Driver 17 for SQL Server",
            ),
            "TrustServerCertificate": os.getenv(
                "DB_TRUST_SERVER_CERTIFICATE",
                "yes",
            ),
        },
    )
    connect_args = {}
else:
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jiu_eat.db")
    connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

對應的環境變數範例：

```bash
export DB_TYPE='mssql'
export DB_HOST='db-server'
export DB_PORT='1433'
export DB_NAME='jiu_eat_1.2'
export DB_USERNAME='jiueat_app'
export DB_PASSWORD='實際密碼'
export DB_DRIVER='ODBC Driver 17 for SQL Server'
export DB_TRUST_SERVER_CERTIFICATE='yes'
```

二選一即可：

- 希望最少改程式：保留現有 `database.py`，設定完整 `DATABASE_URL`。
- 希望正式交接與管理較清楚：採用 `URL.create()` 和分開的環境變數。

## 8. 啟動與連線測試

請先在專案根目錄測試資料庫連線：

```bash
uv run python -c "from backend.database import engine; c = engine.connect(); print('MSSQL connection successful'); c.close()"
```

連線成功後啟動：

```bash
uv run uvicorn backend.main:app --reload
```

測試網址：

- API 文件：`http://127.0.0.1:8000/docs`
- 健康檢查：`http://127.0.0.1:8000/api/health`

再使用 API 新增會員或活動，並至 MSSQL 查詢資料：

```sql
USE jiu_eat_1.2;
GO

SELECT * FROM members;
SELECT * FROM activities;
SELECT * FROM applications;
```

## 9. 現有資料表

目前 SQLAlchemy models 會建立三張主要資料表：

| 資料表 | 用途 | 主要關聯 |
| --- | --- | --- |
| `members` | 會員資料 | 會員可建立活動、提出申請 |
| `activities` | 活動資料 | `organizer_id` → `members.id` |
| `applications` | 活動申請 | `activity_id` → `activities.id`；`member_id` → `members.id` |

`applications` 已設定 `(activity_id, member_id)` 唯一限制，避免同一會員對同一活動重複申請。

## 10. SQLite 舊資料搬移

切換連線不會自動複製 `jiu_eat.db` 的舊資料。若需保留舊資料，建議流程為：

1. 備份 `jiu_eat.db`。
2. 在 MSSQL 建立結構。
3. 依外鍵順序匯入 `members`、`activities`、`applications`。
4. 核對每張表筆數、主鍵和關聯。
5. 驗證完成後才將應用程式正式指向 MSSQL。

正式搬移建議另寫一次性 migration 程式或由 DBA 使用 ETL 工具處理，不要直接刪除原 SQLite 檔案。

## 11. 正式環境注意事項

- 不要將帳號、密碼提交到 Git。
- 限制資料庫帳號權限，只授予應用程式實際需要的權限。
- 正式環境不要依賴 `models.Base.metadata.create_all()` 管理版本；建議導入 Alembic migration。
- 設定連線池、逾時及錯誤監控。
- 使用受信任的 TLS 憑證，並依公司規範設定加密連線。
- 上線前先在測試環境執行 CRUD、外鍵、唯一限制及中文內容測試。
- MSSQL 的 `String` 對應是否為 Unicode 型別會受 dialect 及資料庫設定影響；若公司環境中文存取異常，應將文字欄位明確改用 SQLAlchemy `Unicode`／`UnicodeText` 後再建立 migration。

## 12. 常見錯誤

### 找不到 `pyodbc`

```text
ModuleNotFoundError: No module named 'pyodbc'
```

處理：

```bash
uv add pyodbc
uv sync
```

### 找不到 ODBC Driver

```text
Can't open lib 'ODBC Driver 17 for SQL Server'
```

處理：確認主機已安裝 Driver 17，且 `DB_DRIVER`／連線字串名稱與 `odbcinst -q -d` 顯示完全一致。

### 登入失敗

```text
Login failed for user
```

處理：確認驗證模式、帳號密碼、Database 權限及 SQL Server 是否允許該登入方式。

### 連線逾時

處理：確認主機名稱、Port 1433、防火牆、SQL Server TCP/IP 設定，以及是否需要 VPN。

### 憑證錯誤

處理：測試環境可依規範暫用 `TrustServerCertificate=yes`；正式環境應安裝及信任正確憑證。

## 13. 交接確認清單

- [ ] 執行主機已安裝 ODBC Driver 17 for SQL Server
- [ ] `pyodbc` 已加入相依套件並完成 `uv sync`
- [ ] MSSQL Database 已建立
- [ ] 應用程式帳號及最小必要權限已設定
- [ ] 環境變數已設定，且密碼未寫入 Git
- [ ] Python 資料庫連線測試成功
- [ ] FastAPI 可正常啟動
- [ ] `/docs` 與 `/api/health` 可開啟
- [ ] 會員、活動、申請 CRUD 已測試
- [ ] 中文、日期、外鍵和唯一限制已測試
- [ ] 若需舊資料，已完成搬移與筆數核對

## 14. 修改摘要

最小修改方案如下：

```bash
uv add pyodbc

export DATABASE_URL='mssql+pyodbc://帳號:密碼@主機:1433/jiu_eat_1.2?driver=ODBC+Driver+17+for+SQL+Server&TrustServerCertificate=yes'

uv run python -c "from backend.database import engine; c = engine.connect(); print('MSSQL connection successful'); c.close()"

uv run uvicorn backend.main:app --reload
```

只要 `DATABASE_URL` 正確，現有 API 路由、推薦服務和前端呼叫方式均不需因 SQLite 改 MSSQL 而修改。
