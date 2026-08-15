# JiuEat

這是一個提供測試與示範用的 Python 專案。
本專案使用 **MSSQL（SQL Server）** 作為資料庫（本機 `localhost:1433`，資料庫名為 `jiu_eat_1.2`），需安裝 SQL Server 與 ODBC Driver 17。可透過環境變數 `DATABASE_URL` 抽換為其他關聯式資料庫（如 MySQL、PostgreSQL、SQLite）。 


前後端由同一個 FastAPI 服務提供；推薦功能目前採規則式計分，之後可只替換
`backend/services/recommendation_service.py`，API 與前端不需更動。

## 啟動

於專案根目錄執行以下指令（`uv sync` 會自動建立虛擬環境並安裝依賴）：

```bash
uv sync
uv run uvicorn backend.main:app --reload
```

> 若部署環境沒有 uv，可先建立虛擬環境，再用 `requirements.txt` 安裝依賴（內容與 pyproject.toml 一致）：
> ```bash
> uv venv
> uv pip install -r requirements.txt
> ```

啟動後可瀏覽：

- **網頁：<http://127.0.0.1:8000/>**
- API 文件：<http://127.0.0.1:8000/docs>
- 健康檢查：<http://127.0.0.1:8000/api/health>


## 分層規則

- `routers/`：網址、輸入輸出、HTTP 錯誤
- `services/`：目前只放推薦邏輯；未來可換成 ML
- `models.py`：SQLAlchemy 資料表
- `schemas.py`：Pydantic API 格式
- `frontend/`：HTML、CSS、JavaScript



