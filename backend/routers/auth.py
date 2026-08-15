"""
認證相關 API 路由（backend/routers/auth.py）
=============================================
提供會員的認證功能：
- POST /api/register ：註冊新會員
- POST /api/login    ：會員登入
- POST /api/logout   ：會員登出（前端自行清除 sessionStorage）
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from .. import models, schemas                       # ORM 模型與 Pydantic Schema
from ..common import hash_password, verify_password  # 密碼雜湊與驗證工具
from ..database import get_db                        # 資料庫 Session 依賴
from ..session_tokens import create_token, delete_token   # 登入憑證管理

# 建立路由器：所有端點以 /api 為前綴，標記為 auth 群組
router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/register", response_model=schemas.Member, status_code=201)
def register(data: schemas.MemberRegister, db: Session = Depends(get_db)):
    """
    註冊新會員：驗證 Email 唯一性，建立會員資料
    - Email 一律轉為小寫並去除首尾空白，避免重複註冊
    - 若 Email 已存在，回傳 409 Conflict
    - 密碼以雜湊形式儲存，不存明文
    """
    email = data.email.lower().strip()                       # 標準化 Email（小寫 + 去空白）
    # 檢查 Email 是否已被註冊
    if db.query(models.Member).filter_by(email=email).first():
        raise HTTPException(409, "此 Email 已經註冊")
    # 建立新會員（密碼經雜湊處理），只保存必要的個人資料欄位
    member = models.Member(email=email, password_hash=hash_password(data.password),
        display_name=data.display_name.strip(), gender=data.gender, zodiac=data.zodiac,
        age=data.age.strip(), occupation=data.occupation.strip(),
        city=data.city.strip(), district=data.district.strip(),
        interests=data.interests.strip(), preferred_cuisine=data.preferred_cuisine.strip(),
        bio=data.bio.strip())
    db.add(member); db.commit(); db.refresh(member)   # 寫入資料庫並重新讀取（取得自動產生的 id）
    return member


@router.post("/login", response_model=schemas.LoginResponse)
def login(data: schemas.LoginRequest, db: Session = Depends(get_db)):
    """
    登入：驗證帳號密碼，成功則回傳會員編號與顯示名稱
    - 依 Email 找出會員，再比對密碼雜湊
    - 會員不存在或密碼錯誤皆回傳 401（不洩漏是哪一項錯誤）
    """
    member = db.query(models.Member).filter_by(email=data.email.lower().strip()).first()
    if not member or not verify_password(data.password, member.password_hash):
        raise HTTPException(401, "Email 或密碼錯誤")
    token = create_token(member.id)   # 登入成功：產生一組登入憑證
    return {"member_id": member.id, "display_name": member.display_name, "token": token}


@router.post("/logout")
def logout(authorization: str = Header(default="")):
    """登出：使目前的登入憑證失效（前端同時清除 sessionStorage）"""
    token = authorization.removeprefix("Bearer ").strip()
    if token:
        delete_token(token)
    return {"message": "已登出"}
