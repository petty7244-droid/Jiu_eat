# JiuEat

部署目標：**Northflank（FastAPI＋前端）→ Supabase（PostgreSQL）**。

完整操作請見 [Render → Northflank 搬遷指南](docs/northflank-deployment-guide.md)。新網址部署後由 Northflank 的 Public DNS 取得；原 Render 網址只作為搬遷期間的舊入口。

> 這是提供測試與示範用的 Python 專案。搬遷後部署架構：
> **FastAPI（Northflank）→ PostgreSQL（Supabase）**，資料庫可用 DBeaver 本機連線管理。

## 架構

```text
使用者瀏覽器
    │
    ▼
Northflank（FastAPI 後端 + 前端 SPA）  https://<Public DNS>/
    │  連線（DB_* 環境變數）
    ▼
Supabase（雲端 PostgreSQL）          唯一資料來源
    ▲
    │  本機管理
DBeaver
```

- **Northflank**：執行 FastAPI 後端、掛載前端 SPA（`frontend/`）
- **Supabase**：存放所有資料（members / activities / applications / notifications / activity_photos）
- **DBeaver**：本機資料庫管理工具（檢視／操作資料）

## 快速開始（本機開發）

### 1. 安裝相依套件

```bash
uv sync
```

> 若沒有 uv，可建立虛擬環境後用 `requirements.txt` 安裝：
> ```bash
> python3 -m venv .venv
> source .venv/bin/activate
> pip install -r requirements.txt
> ```

### 2. 設定資料庫連線（.env）

複製 `.env.example` 為 `.env`，填入自己的連線資訊（已有 `.env` 時不要覆蓋）。`.env` 已被 `.gitignore` 忽略，不會提交：

```
DB_TYPE=postgres
DB_HOST=<複製Supabase連線主機>
DB_PORT=5432
DB_NAME=postgres
DB_USERNAME=postgres.<你的專案ref>
DB_PASSWORD=<你的Supabase資料庫密碼>
```

> 連線資訊可在 Supabase Dashboard → **Connect** 取得。

### 3. 啟動本機伺服器

```bash
uv run uvicorn backend.main:app --reload --env-file .env
```

可瀏覽：
- 網頁：<http://127.0.0.1:8000/>
- API 文件：<http://127.0.0.1:8000/docs>
- 健康檢查：<http://127.0.0.1:8000/api/health>

## 部署（Northflank + Supabase）

依照 [完整搬遷指南](docs/northflank-deployment-guide.md) 建立 **Combined service**：

| 欄位 | 值 |
| --- | --- |
| Build type | Dockerfile |
| Dockerfile / Build context | `/Dockerfile` / `/`（Repo 根目錄） |
| Container port | `8000`，HTTP，Public |
| Runtime variables | `APP_ENV=production`、`PORT=8000`，以及原 Render 的全部 `DB_*` |
| Instances | `1`（登入憑證目前儲存在單一程序記憶體） |
| Liveness / Readiness | HTTP `8000`，`/api/health` / `/api/ready` |
| Start command | 留空，使用 Dockerfile 的 CMD |

Dockerfile 預設正式環境，漏設資料庫時會拒絕使用 SQLite。Supabase 沿用原專案，搬遷不需要重新匯入資料。部署後首頁使用同源 `/api`，不必修改前端網址。

### 建立資料表與匯入資料

以下僅供全新資料庫初始化參考；這次沿用 Supabase 搬遷不需要執行。

資料表會在 FastAPI 啟動時由 `create_all` 自動建立。匯入 CSV 資料：

```bash
# 本機連到 Supabase（需先設定 .env）
uv run --env-file .env python scripts/import_csv.py            # 匯入（略過已存在主鍵）
uv run --env-file .env python scripts/import_csv.py --reset    # 先清空再匯入
```

腳本依外鍵順序匯入：`members → activities → applications → notifications → activity_photos`，並自動修正 Postgres 序列。

## 專案結構

- `backend/routers/`：網址、輸入輸出、HTTP 錯誤
- `backend/services/`：目前只放推薦邏輯；未來可換成 ML
- `backend/models.py`：SQLAlchemy 資料表
- `backend/schemas.py`：Pydantic API 格式
- `frontend/`：前端 SPA（HTML、CSS、JavaScript）
- `scripts/import_csv.py`：CSV 匯入資料庫的腳本
- `DB_csv/`：原始匯入資料
- `ml/`：推薦系統訓練腳本
- `docs/database-setup-guide.md`：資料庫建置完整指南（含 DBeaver）
- `Dockerfile`、`.dockerignore`：Northflank 容器建置設定
- `.env.example`：不含密碼的環境變數範本
- `docs/northflank-deployment-guide.md`：部署、驗收與回復舊服務步驟
