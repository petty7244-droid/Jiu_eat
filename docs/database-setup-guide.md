# Jiu-Eat：專案掛載資料庫完整程序（Render + Supabase + DBeaver）

## 1. 目標架構

本專案目前的部署架構：

```text
使用者瀏覽器
    │
    ▼
Render（雲端 FastAPI 服務）          ← 後端 API 與前端 SPA
    │  透過 DB_TYPE 環境變數連線
    ▼
Supabase（雲端 PostgreSQL）          ← 唯一資料來源
    ▲
    │  本機管理 / 驗證
本機 DBeaver                          ← 檢視、編輯、匯入檢查
```

| 層 | 角色 | 位置 |
| --- | --- | --- |
| **Render** | 執行 FastAPI 後端、掛載前端 SPA | 雲端 |
| **Supabase** | 存放所有資料（PostgreSQL） | 雲端 |
| **DBeaver** | 資料庫管理工具（檢視／操作資料） | 本機 |
| **`DB_csv/`** | 原始匯入資料（一次性匯入 Supabase） | 本機 repo |

技術棧：`FastAPI → SQLAlchemy → PostgreSQL（Supabase）`。
SQLAlchemy 已抽象化資料庫差異，切換引擎不需要改 API 路由與 models。

---

## 2. 現況盤點：CSV 與資料表對應

### 2.1 資料表（`backend/models.py` 已定義）

| CSV 檔案 | 資料表 | 資料筆數（不含表頭） | Model |
| --- | --- | --- | --- |
| `members.csv` | `members` | 32 | `Member` |
| `activities.csv` | `activities` | 20 | `Activity` |
| `applications.csv` | `applications` | 34 | `Application` |
| `notifications.csv` | `notifications` | 21 | `Notification` |
| `activity_photos.csv` | `activity_photos` | 0（只有表頭） | `ActivityPhoto`（已於 2026-08 補上） |

### 2.2 外鍵依賴（匯入順序依據）

```text
members（無外鍵）
  └─ activities（organizer_id → members.id）
       └─ applications（activity_id → activities.id, member_id → members.id）
       └─ notifications（activity_id → activities.id, member_id → members.id）
       └─ activity_photos（activity_id → activities.id）
```

**匯入順序必須為：`members → activities → applications → notifications → activity_photos`。**

### 2.3 特殊檔案

| 檔案 | 說明 |
| --- | --- |
| `members_fake.csv` | 2000 筆「假會員」資料，供 `ml/train.py`（FP-Growth）訓練推薦規則用。主程式不需要這張表；推薦規則已內建於 `backend/services/recommendation_service.py` 的 `FP_RULES`。 |

---

## 3. 完整程序總覽

```text
[1] 建立 Supabase 專案（雲端資料庫）並取得連線資訊
        ↓
[2] Render 建立 Web Service 並設定 Build / Start Command
        ↓
[3] 在 Render 填入資料庫環境變數（DB_TYPE=postgres …）
        ↓
[4] 部署 / 重啟 → FastAPI 啟動時自動 create_all 建立資料表
        ↓
[5] 本機 DBeaver 連上 Supabase，確認 5 張表已建立
        ↓
[6] 本機執行 scripts/import_csv.py 匯入 CSV（連到 Supabase）
        ↓
[7] DBeaver / Render Logs 驗證資料筆數與 API 行為
```

---

## 4. 步驟 1：建立 Supabase 專案

1. 前往 <https://supabase.com> 註冊／登入（可用 GitHub 帳號）。
2. 點 **New project**。
3. 填寫：
   - **Organization**：選取或新建一個（例如 `jiu-eat`）。
   - **Project name**：輸入 `jiu-eat`。
   - **Database Password**：設定資料庫密碼，**務必記下並妥善保存**。
   - **Region**：選擇 **Southeast Asia (Singapore)**（離台灣最近、延遲最低）。
   - **Pricing Plan**：選 **Free**。
4. 點 **Create new project**，等待約 1~2 分鐘佈建完成。

### 4.1 取得連線資訊

**Project Settings → Database → Connection string**：

| 方式 | Host | Port | 用途 |
| --- | --- | --- | --- |
| **Direct connection** | `db.<project-ref>.supabase.co` | 5432 | Render／DBeaver 單一連線使用 |
| **Pooler（Transaction mode）** | `aws-0-ap-southeast-1.pooler.supabase.com` | 6543 | 併發多、或 IPv6 連線問題時的備援 |

> - 使用者名稱：direct connection 為 `postgres`；pooler 為 `postgres.<project-ref>`。
> - 若密碼含 `@ : / # %` 等 URL 特殊字元，本專案的 `database.py` 使用 `URL.create()`，
>   可自動正確處理，不需手動 encoding。
> - 忘了密碼：**Settings → Database → Reset database password**。

---

## 5. 步驟 2：Render 部署 FastAPI

### 5.1 建立 Web Service

1. Render Dashboard → **New → Web Service** → 連接你的 GitHub 專案。
2. 依下表設定：

| 欄位 | 值 |
| --- | --- |
| **Root Directory** | **留空**（Repo 根目錄，不要填 `backend/main.py`——它是目錄不是檔案） |
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` |
| **Instance Type** | Free（先開發測試用） |
| **Health Check Path** | `/api/health`（可選） |

> 不要把 Root Directory 設為 `backend`——`requirements.txt` 位於 repo 根目錄，
> 設成 `backend` 會導致 Build Command 找不到該檔。

### 5.2 設定環境變數（關鍵）

Render service → **Environment**，加入（值取自第 4.1 節）：

```
DB_TYPE=postgres
DB_HOST=db.<你的專案ref>.supabase.co
DB_PORT=5432
DB_NAME=postgres
DB_USERNAME=postgres
DB_PASSWORD=<你的資料庫密碼>
```

> ⚠️ **若不設 `DB_TYPE=postgres`，程式會退回 SQLite（`sqlite:///./jiu_eat.db`）**。
> 那會寫在 Render 的臨時磁碟，每次重新部署資料就全部消失。務必設定。

### 5.3 部署與重啟

儲存環境變數後：

1. **Manual Deploy → Deploy latest commit**（或直接 Restart）。
2. 查看 **Logs**，確認啟動無錯誤、`create_all` 已建立資料表。
3. 開啟 service 的公開網址，確認 `/{health}`（`/api/health`）回傳 `{"status":"ok"}`。

> 前端不用額外設定：FastAPI 在 `/` 掛載 `frontend/index.html`（SPA），
> `app.js` 使用 `window.__API_BASE__ || ""` 走**同源**，會自動呼叫 Render 自己的 API。
> 根目錄的 `api-base.js` 是 GitHub Pages 用的舊檔，Render 上不會被載入。

---

## 6. 步驟 3：自動建立資料表

FastAPI 啟動時會執行 `models.Base.metadata.create_all(bind=engine)`（`backend/main.py:24`），
只要第 5.2 節的環境變數正確，**第一次部署啟動就會自動建立 5 張表**
（members、activities、applications、notifications、activity_photos）。

本機也可手動觸發建表（連到 Supabase）：

```bash
export DB_TYPE='postgres'
export DB_HOST='db.<你的專案ref>.supabase.co'
export DB_PORT='5432'
export DB_NAME='postgres'
export DB_USERNAME='postgres'
export DB_PASSWORD='你的密碼'

uv run python -c "from backend import models; from backend.database import engine; models.Base.metadata.create_all(bind=engine); print('Tables created')"
```

> 需要手動 SQL 建表（例如不想先部署）時，可用 Supabase Dashboard → **SQL Editor**
> 執行 `docs/database-setup-guide.md` 內附的 DDL（見附錄 A）。

---

## 7. 步驟 4：本機 DBeaver 連上 Supabase

DBeaver 用來看／管理 Supabase 資料（不需額外寫程式）。

### 7.1 建立連線

1. DBeaver → **Database → New Database Connection**。
2. 選 **PostgreSQL**。
3. 填寫（Driver settings 預設即可）：

| 欄位 | 值 |
| --- | --- |
| **Host** | `db.<你的專案ref>.supabase.co` |
| **Port** | `5432` |
| **Database** | `postgres` |
| **Username** | `postgres` |
| **Password** | 資料庫密碼 |
| **SSL** | 勾選 `Require SSL`（主連線設定頁或 Driver 屬性） |

4. 點 **Test Connection**，成功後 **Finish**。

### 7.2 常見連線問題

- **IPv6 timeout**：部分台灣 ISP 對 Supabase direct connection 有 IPv6 問題。解法：
  - 改用 Pooler：Host `aws-0-ap-southeast-1.pooler.supabase.com`、Port `6543`、Username `postgres.<ref>`；或
  - Supabase → **Networking** 啟用 IPv4 add-on。
- 密碼錯誤：到 Supabase **Settings → Database → Reset database password** 重設後更新。

連上後，在 `public` schema 應可看到 5 張表。

---

## 8. 步驟 5：匯入 CSV 資料

匯入在本機執行（連到 Supabase），不佔用 Render。

### 8.1 前置

- 已安裝 `psycopg2-binary`（專案相依已含）。
- 已設定第 5.2 節的本機環境變數（`DB_TYPE`、`DB_HOST`、`DB_PASSWORD` …）。

### 8.2 執行匯入

```bash
# 本機
export DB_TYPE='postgres'
export DB_HOST='db.<你的專案ref>.supabase.co'
export DB_PASSWORD='你的密碼'

# 第一次匯入
uv run python scripts/import_csv.py

# 需要重來時（先清空再匯入）
uv run python scripts/import_csv.py --reset
```

腳本（`scripts/import_csv.py`）會自動：
1. 依外鍵順序匯入：`members → activities → applications → notifications → activity_photos`
2. 保留 CSV 原 id，不破壞外鍵關聯
3. 重複執行時略過已存在主鍵（冪等）
4. **Postgres 自動 `setval` 修正序列**，避免之後 API 新增資料主鍵衝突

預期輸出筆數：

```text
members.csv       → members         匯入 32 筆
activities.csv    → activities      匯入 20 筆
applications.csv  → applications    匯入 34 筆
notifications.csv → notifications   匯入 21 筆
activity_photos.csv → activity_photos 匯入 0 筆
```

---

## 9. 步驟 6：驗證與測試

### 9.1 DBeaver 驗證資料

在 DBeaver 執行：

```sql
SELECT 'members' AS t, COUNT(*) FROM members
UNION ALL SELECT 'activities', COUNT(*) FROM activities
UNION ALL SELECT 'applications', COUNT(*) FROM applications
UNION ALL SELECT 'notifications', COUNT(*) FROM notifications;
```

預期：`32 / 20 / 34 / 21`。

抽驗外鍵關聯（例如 members 1 → activities 48 → applications 38）：

```sql
SELECT id, display_name, city, interests FROM members WHERE id = 1;
SELECT id, title, category, status FROM activities WHERE id = 32;
SELECT id, activity_id, member_id, status FROM applications WHERE id = 38;
```

### 9.2 API 驗證（Render 公開網址）

| 檢查項目 | 位置 | 預期結果 |
| --- | --- | --- |
| 健康檢查 | `https://<render-service>.onrender.com/api/health` | `{"status":"ok"}` |
| API 文件 | `https://<render-service>.onrender.com/docs` | 正常顯示 |
| 首頁 SPA | `https://<render-service>.onrender.com/` | 活動列表載入 |

登入測試：

```bash
curl -X POST https://<render-service>.onrender.com/api/login \
  -H "Content-Type: application/json" \
  -d '{"email": "jiaming1014@gmail.com", "password": "你的測試密碼"}'
```

> CSV 中的密碼已雜湊，無法得知明文；建議用 `/api/register` 新建一筆帳號做 CRUD 測試。

---

## 10. 本機開發（非 Render）連線 Supabase

不想動 Render 時，本機跑 FastAPI 同樣連 Supabase：

```bash
export DB_TYPE='postgres'
export DB_HOST='db.<你的專案ref>.supabase.co'
export DB_PORT='5432'
export DB_NAME='postgres'
export DB_USERNAME='postgres'
export DB_PASSWORD='你的密碼'

uv run uvicorn backend.main:app --reload
```

連線測試（不啟動伺服器）：

```bash
uv run python -c "from backend.database import engine; c = engine.connect(); print('PostgreSQL connection OK'); c.close()"
```

---

## 11. 備援方案（僅參考）

| 方案 | 說明 |
| --- | --- |
| **MSSQL via Docker** | 原始設計。`DB_TYPE=mssql`，搭配本機 `docker compose up -d db`。 |
| **SQLite** | 本機快速原型。不設 `DB_TYPE` 即為預設 `sqlite:///./jiu_eat.db`，資料不入雲。 |

---

## 12. 成員假資料 `members_fake`（ML 用，可選）

- 2000 筆 0/1 特徵矩陣（40 興趣 + 6 縣市 + 5 活動分類），供 `ml/train.py` 訓練 FP-Growth。
- **主程式不需要**，推薦規則已內建在 `recommendation_service.py` 的 `FP_RULES`。
- 若要重新訓練：先建 `members_fake` 表 → Supabase **Table Editor → Import data from CSV** 匯入該檔 → 修改 `ml/train.py` 連線字串為 Supabase → `python ml/train.py`。

---

## 13. 常見問題

### Render 顯示 `connection failed`（連不上 Supabase）

- 確認 Render 環境變數 `DB_HOST / DB_PORT / DB_NAME / DB_USERNAME / DB_PASSWORD` 與 Supabase Connection string 一致。
- 確認密碼正確。
- Supabase 強制 SSL，`database.py` 已內建 `sslmode=require`。

### Render 部署後資料「看起來正常」但每次重啟都不見

- 代表退回 SQLite 了：確認 **`DB_TYPE=postgres`** 已在 Render Environment 設定。
- 重新部署後資料落在臨時磁碟，`create_all` 重建的是空表。

### 匯入後新增資料主鍵衝突

```text
duplicate key value violates unique constraint "members_pkey"
```

- 原因：直接指定 id 匯入，Postgres 的 `SERIAL` 序列沒有前進。
- 解決：執行 `uv run python scripts/import_csv.py`（內建 `fix_sequences()`）；
  或手動執行
  ```sql
  SELECT setval(pg_get_serial_sequence('members', 'id'), (SELECT MAX(id) FROM members));
  ```

### DBeaver 連不上（timeout）

- 多為 IPv6 問題：改用 Pooler（`aws-0-ap-southeast-1.pooler.supabase.com:6543`，user 加 `.ref`）或啟用 Supabase IPv4 add-on。

### Supabase 免費專案被暫停

- 閒置約 7 天會進入 Pause，連線失敗；Dashboard 按 **Restore** 即可恢復，資料不會遺失。

---

## 14. 檢查清單

- [ ] Supabase 專案已建立，密碼已保存、未寫入 Git
- [ ] Render Web Service 建立完成：
  - Root Directory 留空、Build `pip install -r requirements.txt`
  - Start `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- [ ] Render Environment 已設定 `DB_TYPE=postgres` 與 `DB_*` 連線變數
- [ ] Render 部署成功，Logs 無錯誤，`/api/health` 回 `ok`
- [ ] Supabase Table Editor（或 DBeaver）看到 5 張表
- [ ] 本機 DBeaver 連上 Supabase（PostgreSQL、SSL require）
- [ ] 本機執行 `scripts/import_csv.py` 匯入成功
- [ ] 筆數核對：32 / 20 / 34 / 21（DBeaver COUNT）
- [ ] 外鍵與中文資料抽驗正常
- [ ] 登入／註冊 CRUD 測試通過
- [ ] （選）`members_fake` 是否匯入已決定

---

## 附錄 A：手動建表 DDL（Supabase SQL Editor）

若不想依賴 `create_all` 自動建表，可在 **Supabase → SQL Editor** 執行：

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