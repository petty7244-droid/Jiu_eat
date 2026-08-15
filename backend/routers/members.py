"""
會員資料相關 API 路由（backend/routers/members.py）
=====================================================
提供會員個人資料的存取與更新：
- GET /api/members/{member_id}           ：取得單一會員資料
- PUT /api/members/{member_id}           ：更新會員個人資料
- GET /api/members/{member_id}/activities：取得會員建立的活動與提出的申請
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..common import activity_json, application_json, get_current_member, get_optional_member, member_or_404
from ..database import get_db

# 建立路由器：所有端點以 /api/members 為前綴，標記為 members 群組
router = APIRouter(prefix="/api/members", tags=["members"])


@router.get("/{member_id}")
def get_member(member_id: int, current: models.Member | None = Depends(get_optional_member), db: Session = Depends(get_db)):
    """取得單一會員資料（找不到會員時由 member_or_404 回傳 404）
    - 若檢視的是自己，回傳完整資料（含 Email）
    - 檢視他人時只回傳公開資料（不含 Email），避免洩漏個資
    """
    member = member_or_404(db, member_id)
    if current is not None and current.id == member_id:
        return schemas.Member.model_validate(member)
    return schemas.MemberPublic.model_validate(member)


@router.put("/{member_id}", response_model=schemas.Member)
def update_member(member_id: int, data: schemas.MemberUpdate, current: models.Member = Depends(get_current_member), db: Session = Depends(get_db)):
    """
    更新會員個人資料（逐欄位更新，字串自動去除空白）
    - 僅限本人可修改（以目前登入身分 current 比對）
    - 使用 data.model_dump() 取出所有欄位
    - 字串欄位會先 strip() 去除首尾空白再存回
    """
    if member_id != current.id:
        raise HTTPException(403, "只能修改自己的資料")
    member = member_or_404(db, member_id)
    for key, value in data.model_dump().items():
        setattr(member, key, value.strip() if isinstance(value, str) else value)
    db.commit(); db.refresh(member)   # 儲存變更並重新讀取
    return member


@router.get("/{member_id}/activities")
def member_activities(member_id: int, current: models.Member = Depends(get_current_member), db: Session = Depends(get_db)):
    """
    取得會員建立的活動與提出的申請列表
    - 僅限本人可查看（以目前登入身分 current 比對）
    - 回傳兩個列表：created（建立的活動）、applications（提出的申請）
    - 建立的活動依活動時間排序
    - 提出的申請依申請時間倒序（最新在前）
    """
    if member_id != current.id:
        raise HTTPException(403, "只能查看自己的資料")
    member_or_404(db, member_id)   # 先確認會員存在
    # 查詢該會員建立的活動（依活動時間排序）
    created = db.query(models.Activity).filter_by(organizer_id=member_id).order_by(models.Activity.activity_date).all()
    # 查詢該會員提出的申請（依申請時間倒序）
    applications = db.query(models.Application).filter_by(member_id=member_id).order_by(models.Application.created_at.desc()).all()
    return {"created": [activity_json(x) for x in created],
            "applications": [application_json(x) for x in applications]}
