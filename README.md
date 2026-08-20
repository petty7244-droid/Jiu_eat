# JiuEat

線上測試網址：**https://jiu-eat.onrender.com/**

> 這是提供測試與示範用的 Python 專案。目前部署架構：
> **FastAPI（Render）→ PostgreSQL（Supabase）**，資料庫可用 DBeaver 本機連線管理。

## 架構

```text
使用者瀏覽器
    │
    ▼
Render（FastAPI 後端 + 前端 SPA）    https://jiu-eat.onrender.com/
    │  連線（DB_* 環境變數）
    ▼
Supabase（雲端 PostgreSQL）          唯一資料來源
    ▲
    │  本機管理
DBeaver
```

- **Render**：執行 FastAPI 後端、掛載前端 SPA（`frontend/`）
- **Supabase**：存放所有資料（members / activities / applications / notifications / activity_photos）
- **DBeaver**：本機資料庫管理工具（檢視／操作資料）

## 快速開始（本機開發）

### 1. 安裝相依套件

```bash
uv sync
```

> 若沒有 uv，可建立虛擬環境後用 `requirements.txt` 安裝：
> ```bash
> uv venv
> uv pip install -r requirements.txt
> ```

### 2. 設定資料庫連線（.env）

建立 `.env`（已被 `.gitignore` 忽略，不會提交）：

```
DB_TYPE=postgres
DB_HOST=aws-0-ap-southeast-2.pooler.supabase.com
DB_PORT=5432
DB_NAME=postgres
DB_USERNAME=postgres.<你的專案ref>
DB_PASSWORD=<你的Supabase資料庫密碼>
```

> 連線資訊可在 Supabase Dashboard → **Project Settings → Database → Connection string** 取得。

### 3. 啟動本機伺服器

```bash
uv run uvicorn backend.main:app --reload
```

可瀏覽：
- 網頁：<http://127.0.0.1:8000/>
- API 文件：<http://127.0.0.1:8000/docs>
- 健康檢查：<http://127.0.0.1:8000/api/health>

## 部署（Render + Supabase）

### Supabase 建立資料庫

1. 至 <https://supabase.com> 建立專案，記錄 Database Password。
2. 取得連線資訊（Settings → Database → Connection string）。

### Render 部署 FastAPI

| 欄位 | 值 |
| --- | --- |
| **Root Directory** | 留空（Repo 根目錄） |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` |

環境變數（Environment）：

```
DB_TYPE=postgres
DB_HOST=aws-0-ap-southeast-2.pooler.supabase.com
DB_PORT=5432
DB_NAME=postgres
DB_USERNAME=postgres.<你的專案ref>
DB_PASSWORD=<你的Supabase資料庫密碼>
```

> ⚠️ 務必設定 `DB_TYPE=postgres`，否則會退回 SQLite，重新部署時資料會消失。

### 建立資料表與匯入資料

資料表會在 FastAPI 啟動時由 `create_all` 自動建立。匯入 CSV 資料：

```bash
# 本機連到 Supabase（需先設定 .env）
uv run python scripts/import_csv.py            # 匯入（略過已存在主鍵）
uv run python scripts/import_csv.py --reset    # 先清空再匯入
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