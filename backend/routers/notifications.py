"""
活動通知 API 路由（backend/routers/notifications.py）
======================================================
提供會員的通知查詢與已讀管理：
- GET  /api/notifications                  ：取得目前會員的通知列表（最新在前）
- GET  /api/notifications/unread-count     ：取得目前會員的未讀通知數量
- PUT  /api/notifications/read-all         ：將目前會員的所有通知標記為已讀
- PUT  /api/notifications/{id}/read        ：將單筆通知標記為已讀
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..common import get_current_member, notification_json
from ..database import get_db

# 建立路由器：所有端點以 /api/notifications 為前綴，標記為 notifications 群組
router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=List[schemas.Notification])
def list_notifications(limit: int = Query(50, ge=1, le=100),
                       current: models.Member = Depends(get_current_member), db: Session = Depends(get_db)):
    """
    取得目前會員的通知列表
    - 僅限本人查看（以目前登入身分 current 比對）
    - 依通知時間倒序，最新在前
    - limit：回傳筆數上限（1~100，預設 50），避免一次載入過多通知
    """
    items = db.query(models.Notification).filter_by(member_id=current.id).order_by(models.Notification.created_at.desc()).limit(limit).all()
    return [notification_json(x) for x in items]


@router.get("/unread-count")
def unread_count(current: models.Member = Depends(get_current_member), db: Session = Depends(get_db)):
    """取得目前會員的未讀通知數量（供前端鈴鐺徽章顯示）"""
    count = db.query(models.Notification).filter_by(member_id=current.id, is_read=0).count()
    return {"count": count}


@router.put("/read-all")
def read_all(current: models.Member = Depends(get_current_member), db: Session = Depends(get_db)):
    """將目前會員的所有通知標記為已讀"""
    db.query(models.Notification).filter_by(member_id=current.id, is_read=0).update({models.Notification.is_read: 1})
    db.commit()
    return {"message": "已全部標記為已讀"}


@router.put("/{notification_id}/read")
def mark_read(notification_id: int, current: models.Member = Depends(get_current_member), db: Session = Depends(get_db)):
    """將單筆通知標記為已讀（僅限收件人本人）"""
    notification = db.get(models.Notification, notification_id)
    if not notification: raise HTTPException(404, "找不到通知")
    if notification.member_id != current.id: raise HTTPException(403, "只能操作自己的通知")
    notification.is_read = 1
    db.commit()
    return {"message": "已標記為已讀"}
