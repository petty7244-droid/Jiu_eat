# JiuEat：從 Render 搬到 Northflank

本次搬遷範圍是 FastAPI 和它提供的 `frontend/` 網頁，Supabase 沿用原專案。資料庫不必匯出、重建或重新匯入。程式碼準備完成並不代表雲端已部署，需完成以下 Northflank 帳號操作。

## 1. 將修改推送到 GitHub

先檢視差異，提交本次的 `Dockerfile`、`.dockerignore`、`.env.example`、`backend/main.py`、`backend/database.py`、`README.md`、本指南與 `tests/test_deployment.py`，再推送到要部署的分支。不要加入 `.env`。根目錄 `main.py` 是原本的範例程式，真正的 API 入口是 `backend.main:app`。

## 2. 建立 Northflank 專案與服務

1. 登入 <https://app.northflank.com/>，連接 GitHub 並允許存取 `Jiu_eat` repository。
2. 建立 Project，例如 `jiu-eat`，選擇適合使用者與既有 Supabase 資料庫的區域；以控制台提供的區域為準。
3. 專案內選擇 **Create new → Service → Combined**，服務名稱例如 `jiu-eat-web`。
4. Repository 選 `Jiu_eat`，Branch 選剛才推送的分支（不要假設一定叫 main）。
5. Build options 選 **Dockerfile**，Dockerfile location 填 `/Dockerfile`，Build context 填 `/`（repository 根目錄）。不要選 `backend/`，容器還需要 `frontend/` 與 `requirements.txt`。
6. **Docker CMD override 留空**，不需要另外填 Render 的 Build / Start command。
7. Resources 的 Instances 設為 **1**，關閉自動增加副本。CPU／RAM 依帳號可用方案和建置、執行用量選擇，建立前查看顯示的費用。

容器使用 Python 3.12、非 root 使用者，執行：

```sh
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1
```

`PORT` 可調整，但要同時修改 Networking 和 health checks 的埠；首次部署建議固定 `8000`。現有登入 token 存在程序記憶體，所以不能增加 worker 或副本；重新部署、重啟、平台替換容器後需重新登入，滾動更新期間也可能短暫失去登入狀態。未來若要多副本，需先改為共用的登入憑證儲存。

## 3. 搬移 Runtime variables

在服務的 **Environment variables / Runtime variables** 填入下表。這些是執行階段設定，不是 Build arguments。

| 變數 | 填入內容 |
| --- | --- |
| `APP_ENV` | `production`（Dockerfile 已預設，控制台明確填入更容易檢查） |
| `PORT` | `8000` |
| `DB_TYPE` | `postgres`（原本用 `supabase` 也可以） |
| `DB_HOST` | 複製 Render 原值 |
| `DB_PORT` | 複製 Render 原值，不能任意改成網站的 8000 |
| `DB_NAME` | 複製 Render 原值，通常為 `postgres` |
| `DB_USERNAME` | 複製 Render 原值，pooler 使用者名稱可能包含專案 ref |
| `DB_PASSWORD` | 複製 Render 原值，是資料庫密碼，不是 Supabase API key |
| `DB_SSLMODE` | `require`，或沿用既有更嚴格且可用的 SSL 設定 |

密碼直接貼原值，不要自行 URL encode，也不要額外加引號。正式密碼只填在平台秘密變數中，不要提交到 GitHub。

目前以 `DB_TYPE=postgres` 搭配 `DB_*` 為準，無需新增 `DATABASE_URL`。缺少設定會使啟動失敗，不會偷偷建立一份空的本機 SQLite 資料庫。容器建置不會連線 Supabase，啟動時才會連線並執行原有的 `create_all`，建立不存在的資料表；不會清空既有資料，也不會自動更新既有表格結構。

## 4. 網路與健康檢查

在 **Networking**（建立後可由 **Run → Networking** 修改）確認：

| 欄位 | 值 |
| --- | --- |
| Port name | `http` |
| Container port | `8000` |
| Protocol | HTTP |
| Public | 開啟 |

Dockerfile 的 `EXPOSE 8000` 可供平台偵測埠，仍需確認 Public 已開啟。使用 Northflank 顯示的 HTTPS Public DNS，瀏覽器網址不加 `:8000`。

在 **Health checks** 新增兩個 HTTP probe：

| 類型 | 埠與路徑 | 用途 |
| --- | --- | --- |
| Liveness | `8000`，`/api/health` | API 程序是否正常；不查資料庫 |
| Readiness | `8000`，`/api/ready` | 執行 `SELECT 1`，資料庫錯誤回傳 503，暫停導流 |

可先設 initial delay 20 秒、period 30 秒、timeout 10 秒、failure threshold 3，再依實際啟動時間調整。不要把 `/api/ready` 設為 liveness，以免資料庫故障引發容器反覆重啟。

## 5. 建立服務與驗收

點 **Create service**。查看 Build logs 是否成功安裝套件，Runtime logs 是否出現 `Application startup complete`。

取得 Public DNS 後逐一確認：

1. `https://<Public DNS>/api/health` 回傳 `{"status":"ok"}`。
2. `https://<Public DNS>/api/ready` 回傳 `{"status":"ok"}`。
3. `https://<Public DNS>/` 正常顯示首頁、圖片、樣式；`/docs` 可開啟。
4. 使用既有帳號重新登入，檢查既有活動、報名、收藏等資料仍存在。
5. 用測試帳號完成一次建立活動／報名等操作，確認資料寫入同一個 Supabase 專案。

`frontend/js/app.js` 預設呼叫同源 `/api/...`，因此本次不必更換 API 網址。根目錄的 `index.html`、`login.html` 與 `api-base.js` 是另一套靜態頁，並不是 FastAPI `/` 目前提供的 SPA。

若另有 GitHub Pages 或其他獨立前端，必須將該前端的 API base 改為新 HTTPS Public DNS；必要時在 Northflank 設 `CORS_ORIGINS=https://你的前端網域`，多個來源以逗號分隔，不含路徑或尾端斜線。不要把 GitHub Pages 的 repository 路徑放入 origin。未設定時維持既有允許所有來源的行為。

## 6. 切換入口並保留回復方式

驗收通過後，更新對外分享的網站連結、README 網址與任何外部監控。如果有自訂網域，依 Northflank Domains 指引將網域連至 public port，完成 DNS 與 TLS 驗證後再切換流量。`jiu-eat.onrender.com` 是 Render 網域，不能直接搬到 Northflank。

先保留 Render 服務，確認新站穩定後再於 Render 停用舊服務。若新站有問題，可暫時恢復舊網址／自訂網域路由至 Render，資料仍在同一個 Supabase；登入需重新建立。不要刪除 Supabase，也不要執行 CSV 匯入的 `--reset`。

## 常見問題

| 現象 | 檢查項目 |
| --- | --- |
| 502／網站連不上 | Build、Runtime logs、Public HTTP 8000、`PORT=8000`、CMD override 是否留空 |
| 「正式環境不可使用 SQLite」 | 漏了 `DB_TYPE=postgres` 或資料庫設定填在 Build arguments 而非 Runtime variables |
| `DB_HOST`／`DB_PASSWORD` 缺少 | 補齊 Runtime variables 後重新部署 |
| 資料庫認證或連線錯誤 | 比對原 Render 的全部 `DB_*`，確認 Supabase 未暫停；若有網路限制，允許新服務出口 |
| Supabase 直接連線主機無法到達 | 在 Supabase Connect 取得適合部署網路的 Session pooler 設定，整組複製 host、port、username，不要只替換主機 |
| 首頁正常但資料為空 | 確認連到原本 Supabase project/database，未建立新專案 |
| 反覆要求登入 | 確認只有 1 instance、1 worker；部署與重啟後重新登入屬現有設計 |

## 本機驗證

不碰正式資料庫的程式檢查：

```sh
uv run python -m unittest discover -s tests -v
```

Docker 建置與啟動（`.env` 須已填入資料庫設定；這會連線該資料庫）：

```sh
docker build -t jiu-eat:northflank .
docker run --rm --env-file .env -e APP_ENV=production -p 8000:8000 jiu-eat:northflank
```

## 官方文件

- [建立 Combined service](https://northflank.com/docs/v1/application/getting-started/build-and-deploy-your-code)
- [Dockerfile 與 build context](https://northflank.com/docs/v1/application/build/build-with-a-dockerfile)
- [Runtime variables](https://northflank.com/docs/v1/application/run/inject-runtime-variables)
- [Networking / Ports](https://northflank.com/docs/v1/application/network/configure-ports)
- [Health checks](https://northflank.com/docs/v1/application/observe/configure-health-checks)
- [Supabase 連線方式與 Session pooler](https://supabase.com/docs/guides/database/connecting-to-postgres)
