"""
FastAPI 應用程式主入口（backend/main.py）
=========================================
本檔案是整個後端服務的進入點，負責：
1. 啟動時自動建立資料庫資料表（若尚未存在）
2. 建立 FastAPI 應用程式實例
3. 設定 CORS（跨域資源共享），方便前端開發
4. 註冊所有 API 路由（auth / members / activities / applications / recommendations）
5. 掛載前端靜態檔案（CSS、JS），並提供首頁與健康檢查端點
"""

from pathlib import Path    # 處理檔案路徑（定位前端靜態目錄）

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware      # CORS 中介層
from fastapi.responses import FileResponse               # 回傳檔案（首頁 HTML）
from fastapi.staticfiles import StaticFiles              # 掛載靜態檔案目錄

from . import models                          # ORM 模型（用於建立資料表）
from .database import engine                  # 資料庫引擎
from .routers import activities, applications, auth, members, notifications, recommendations  # API 路由模組

# 自動建立資料表（若不存在）：啟動時掃描所有模型並建立對應的資料表
models.Base.metadata.create_all(bind=engine)

# 建立 FastAPI 應用程式實例，並設定 API 名稱與版本
app = FastAPI(title="Jiu-Eat API", version="0.1.0")

# 設定 CORS（允許所有來源，方便開發測試）
# - allow_origins=["*"]：允許任何網域存取（正式環境建議限定白名單）
# - allow_credentials=False：本專案登入狀態存於 sessionStorage（非 Cookie），無需攜帶認證資訊；
#   且 wildcard origin 依規範不可與 credentials 並用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],      # 允許所有 HTTP 方法（GET/POST/PUT/DELETE...）
    allow_headers=["*"],      # 允許所有請求標頭
)

# 註冊 API 路由
app.include_router(auth.router)               # 認證相關（登入/登出/註冊）
app.include_router(members.router)            # 會員資料
app.include_router(activities.router)         # 活動管理
app.include_router(applications.router)       # 活動申請
app.include_router(notifications.router)      # 活動通知
app.include_router(recommendations.router)    # 推薦系統

# 前端靜態檔案目錄：指向專案根目錄下的 frontend 資料夾
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")   # 掛載樣式表
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")      # 掛載前端腳本


@app.get("/api/health", tags=["system"])
def health():
    """健康檢查端點，回傳 API 是否正常運作（供監控或前端測試連線）"""
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def frontend_home():
    """首頁：回傳前端 index.html（讓瀏覽器存取根路徑時顯示單頁應用程式）"""
    return FileResponse(FRONTEND_DIR / "index.html")


if __name__ == "__main__":
    # 直接執行本檔案時，啟動 uvicorn 開發伺服器（啟用自動重載）
    import uvicorn
    uvicorn.run("backend.main:app", reload=True)
