# JiuEat

這是一個提供測試與示範用的 Python 專案。
本專案使用 **MSSQL（SQL Server）** 作為資料庫，後端與資料庫皆以 **Docker Compose** 啟動。

## 啟動（Docker Compose，推薦）

需要 Docker Desktop（或 Docker Engine + Compose 外掛）。

```bash
docker compose up -d --build
```

啟動後可瀏覽：

- **網頁：<http://127.0.0.1:8000/>**
- API 文件：<http://127.0.0.1:8000/docs>
- 健康檢查：<http://127.0.0.1:8000/api/health>

停止服務：`docker compose down`（資料保留在 volume，`-v` 才會刪除）
查看日誌：`docker compose logs -f backend`

### 可調整的環境變數

| 變數 | 預設值 | 說明 |
| --- | --- | --- |
| `MSSQL_SA_PASSWORD` | `Aa123456` | SQL Server `sa` 密碼（啟動前設定，日後修改會造成連線失敗） |

若要在其他機器上設定不同密碼：

```bash
MSSQL_SA_PASSWORD=YourPassword docker compose up -d --build
```

## 本機啟動（備案）

若想在本機（非 Docker）執行，需自行安裝 SQL Server 與 ODBC Driver，
並透過環境變數提供連線參數：

```bash
uv sync
export MSSQL_SERVER=localhost MSSQL_PORT=1433 MSSQL_DATABASE=jiu_eat_1.2 \
       MSSQL_USER=sa MSSQL_SA_PASSWORD=your_password
uv run uvicorn backend.main:app --reload
```

連線字串也可以直接用 `DATABASE_URL` 完全覆寫（例如改用 SQLite：`sqlite:///./jiu_eat.db`）。

> 若部署環境沒有 uv，可先建立虛擬環境，再用 `requirements.txt` 安裝依賴（內容與 pyproject.toml 一致）：
> ```bash
> uv venv
> uv pip install -r requirements.txt
> ```

- `routers/`：網址、輸入輸出、HTTP 錯誤
- `services/`：目前只放推薦邏輯；未來可換成 ML
- `models.py`：SQLAlchemy 資料表
- `schemas.py`：Pydantic API 格式
- `frontend/`：HTML、CSS、JavaScript



