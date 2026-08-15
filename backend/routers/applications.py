"""
活動申請狀態管理 API 路由（backend/routers/applications.py）
============================================================
提供發起人審核申請與申請人取消報名的功能：
- PUT /api/applications/{application_id}/approve：核准申請（僅限發起人）
- PUT /api/applications/{application_id}/reject ：拒絕申請（僅限發起人）
- PUT /api/applications/{application_id}/cancel ：取消申請（僅限申請人自己）

所有操作共用 change_status() 函式進行權限與狀態檢查。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..common import application_json, get_current_member, with_row_lock
from ..database import get_db

# 建立路由器：所有端點以 /api/applications 為前綴，標記為 applications 群組
router = APIRouter(prefix="/api/applications", tags=["applications"])


def change_status(application_id: int, current: models.Member, status: str, db: Session):
    """
    變更申請狀態的共用函式（供 approve / reject / cancel 三個端點呼叫）
    - cancelled ：僅限申請人自己取消
    - approved/rejected：僅限活動發起人審核
    - approved 時會檢查活動名額是否已滿，滿了則回傳 400
    """
    application = db.get(models.Application, application_id)
    if not application: raise HTTPException(404, "找不到申請")
    # 權限檢查：取消限本人、審核限發起人（以目前登入身分 current 比對）
    if status == "cancelled":
        if application.member_id != current.id: raise HTTPException(403, "只能取消自己的申請")
        # 已被拒絕的申請不可再取消報名
        if application.status == "rejected": raise HTTPException(400, "已被拒絕的申請無法取消")
    elif application.activity.organizer_id != current.id:
        raise HTTPException(403, "只有發起人可以審核")
    # 防呆：申請已是目標狀態時不重複操作
    if application.status == status and status in ("approved", "rejected", "cancelled"):
        raise HTTPException(400, "該申請已是此狀態")
    # 核准時檢查名額：以列鎖串行化核准請求，避免並發同時核准導致超賣
    # 註：SQL Server 會編譯成 WITH (UPDLOCK, HOLDLOCK)（SQLAlchemy 的 with_for_update() 在 MSSQL 會被靜默忽略）
    if status == "approved":
        activity = with_row_lock(db.query(models.Activity).filter(models.Activity.id == application.activity_id), models.Activity).first()
        count = db.query(models.Application).filter_by(activity_id=application.activity_id, status="approved").count()
        if count >= activity.max_participants: raise HTTPException(400, "活動名額已滿")
    # 發起人審核（核准/拒絕）後，建立通知給申請人，告知審核結果
    if status in ("approved", "rejected"):
        verb = "核准" if status == "approved" else "拒絕"
        db.add(models.Notification(
            member_id=application.member_id,
            activity_id=application.activity_id,
            message=f"{application.activity.organizer.display_name} 已{verb}你報名「{application.activity.title}」",
        ))
    application.status = status; db.commit(); db.refresh(application)   # 更新狀態並儲存
    return application_json(application)


@router.put("/{application_id}/approve", response_model=schemas.Application)
def approve(application_id: int, current: models.Member = Depends(get_current_member), db: Session = Depends(get_db)):
    """核准申請（僅限活動發起人）"""
    return change_status(application_id, current, "approved", db)


@router.put("/{application_id}/reject", response_model=schemas.Application)
def reject(application_id: int, current: models.Member = Depends(get_current_member), db: Session = Depends(get_db)):
    """拒絕申請（僅限活動發起人）"""
    return change_status(application_id, current, "rejected", db)


@router.put("/{application_id}/cancel", response_model=schemas.Application)
def cancel(application_id: int, current: models.Member = Depends(get_current_member), db: Session = Depends(get_db)):
    """取消申請（僅限申請人自己）"""
    return change_status(application_id, current, "cancelled", db)
