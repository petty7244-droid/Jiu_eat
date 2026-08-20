"""
活動追蹤 API 路由（backend/routers/favorites.py）
====================================================
提供會員追蹤（收藏）活動的功能：
- GET    /api/favorites            ：取得目前會員追蹤的活動列表
- GET    /api/favorites/ids        ：取得目前會員追蹤的活動編號列表（供前端愛心狀態）
- POST   /api/favorites/{activity_id}  ：追蹤某個活動（加入愛心）
- DELETE /api/favorites/{activity_id}  ：取消追蹤某個活動（移除愛心）
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..common import activity_json, activity_or_404, get_current_member
from ..database import get_db

# 建立路由器：所有端點以 /api/favorites 為前綴，標記為 favorites 群組
router = APIRouter(prefix="/api/favorites", tags=["favorites"])


@router.get("", response_model=List[schemas.Activity])
def list_favorites(current: models.Member = Depends(get_current_member), db: Session = Depends(get_db)):
    """
    取得目前會員追蹤的活動列表
    - 僅限本人查看（以目前登入身分 current 比對）
    - 依活動時間排序，方便會員中心「追蹤活動」分頁顯示
    """
    favorites = db.query(models.Favorite).filter_by(member_id=current.id).all()
    activities = [f.activity for f in favorites]
    activities.sort(key=lambda a: a.activity_date)
    return [activity_json(x) for x in activities]


@router.get("/ids")
def favorite_ids(current: models.Member = Depends(get_current_member), db: Session = Depends(get_db)):
    """取得目前會員追蹤的活動編號列表（供前端判斷愛心是否點亮）"""
    ids = [f.activity_id for f in db.query(models.Favorite).filter_by(member_id=current.id).all()]
    return {"ids": ids}


@router.post("/{activity_id}", status_code=201)
def add_favorite(activity_id: int, current: models.Member = Depends(get_current_member), db: Session = Depends(get_db)):
    """
    追蹤某個活動（加入愛心）
    - 活動不存在時回傳 404
    - 已追蹤過則回傳 409，避免重複追蹤
    """
    activity_or_404(db, activity_id)   # 先確認活動存在
    existing = db.query(models.Favorite).filter_by(activity_id=activity_id, member_id=current.id).first()
    if existing: raise HTTPException(409, "你已經追蹤這個活動")
    db.add(models.Favorite(activity_id=activity_id, member_id=current.id))
    db.commit()
    return {"message": "已加入追蹤"}


@router.delete("/{activity_id}")
def remove_favorite(activity_id: int, current: models.Member = Depends(get_current_member), db: Session = Depends(get_db)):
    """
    取消追蹤某個活動（移除愛心）
    - 尚未追蹤則回傳 404
    """
    favorite = db.query(models.Favorite).filter_by(activity_id=activity_id, member_id=current.id).first()
    if not favorite: raise HTTPException(404, "你尚未追蹤這個活動")
    db.delete(favorite)
    db.commit()
    return {"message": "已取消追蹤"}