"""
活動相關 API 路由（backend/routers/activities.py）
===================================================
提供聚會活動的完整 CRUD 與申請功能：
- GET    /api/activities                          ：活動列表（含關鍵字/分類/城市篩選）
- GET    /api/activities/{activity_id}            ：單一活動詳細資料
- POST   /api/activities                          ：建立新活動
- PUT    /api/activities/{activity_id}            ：更新活動（僅限發起人）
- DELETE /api/activities/{activity_id}            ：刪除活動（僅限發起人）
- POST   /api/activities/{activity_id}/applications：申請參加活動
- GET    /api/activities/{activity_id}/applications：查看申請列表（僅限發起人）
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select                      # OR 條件的 SQL 篩選、select 陳述式
from sqlalchemy.orm import Session

from .. import models, schemas
from ..common import activity_json, activity_or_404, application_json, get_current_member, get_optional_member, taipei_now, validate_activity, with_row_lock
from ..database import get_db
from ..models import Member

# 建立路由器：所有端點以 /api/activities 為前綴，標記為 activities 群組
router = APIRouter(prefix="/api/activities", tags=["activities"])


@router.get("", response_model=List[schemas.Activity])
def list_activities(keyword: Optional[str] = None, category: Optional[str] = None,
                    city: Optional[str] = None, limit: int = Query(50, ge=1, le=100),
                    db: Session = Depends(get_db)):
    """
    取得活動列表：支援關鍵字搜尋、分類篩選、城市篩選
    - 只列出「開放報名」且「活動時間晚於現在」的活動
    - keyword：比對活動名稱、說明、城市、地點、發起人名稱（模糊搜尋）
    - category：依分類精準篩選
    - city：依城市模糊篩選
    - limit：回傳筆數上限（1~100，預設 50）
    """
    # 基本條件：狀態為 open 且活動時間尚未過期
    query = db.query(models.Activity).filter_by(status="open").filter(models.Activity.activity_date > taipei_now())
    # 關鍵字搜尋：匹配活動名稱、說明、城市、地點、發起人名稱
    if keyword:
        like = f"%{keyword.strip()}%"                              # 模糊搜尋用的萬用字元
        subq = select(models.Member.id).where(models.Member.display_name.ilike(like))  # 先找出名稱符合的發起人
        query = query.filter(or_(models.Activity.title.ilike(like), models.Activity.description.ilike(like), models.Activity.city.ilike(like), models.Activity.location_name.ilike(like), models.Activity.organizer_id.in_(subq)))
    if category: query = query.filter_by(category=category)  # 依分類篩選
    if city: query = query.filter(models.Activity.city.ilike(f"%{city.strip()}%"))  # 依城市篩選
    return [activity_json(x) for x in query.order_by(models.Activity.activity_date).limit(limit).all()]


@router.get("/{activity_id}", response_model=schemas.Activity)
def get_activity(activity_id: int, current: Optional[Member] = Depends(get_optional_member), db: Session = Depends(get_db)):
    """
    取得單一活動的詳細資料
    - 若已登入，回應中會額外包含該會員的申請狀態
    """
    return activity_json(activity_or_404(db, activity_id), member_id=current.id if current else None)


@router.post("", response_model=schemas.Activity, status_code=201)
def create_activity(data: schemas.ActivityCreate, current: Member = Depends(get_current_member), db: Session = Depends(get_db)):
    """
    建立新活動：驗證活動時間合理，發起人為目前登入者
    - 發起人取目前登入會員（current）
    - 再驗證時間合理性（validate_activity）
    """
    validate_activity(data)
    activity = models.Activity(organizer_id=current.id, **data.model_dump())   # 將 Schema 欄位轉為模型並建立
    db.add(activity); db.commit(); db.refresh(activity)
    return activity_json(activity)


@router.put("/{activity_id}", response_model=schemas.Activity)
def update_activity(activity_id: int, data: schemas.ActivityUpdate, current: Member = Depends(get_current_member), db: Session = Depends(get_db)):
    """
    更新活動：僅限發起人可修改
    - 檢查目前登入者是否為發起人（organizer_id 比對）
    - 非發起人修改回傳 403
    - 更新前同樣驗證活動時間合理性
    """
    activity = activity_or_404(db, activity_id)
    if activity.organizer_id != current.id: raise HTTPException(403, "只有發起人可以修改活動")
    if activity.deadline <= taipei_now() or activity.activity_date <= taipei_now():
        raise HTTPException(400, "活動已截止報名或已開始，無法修改")
    validate_activity(data)
    for key, value in data.model_dump().items(): setattr(activity, key, value)   # 逐欄位更新
    db.commit(); db.refresh(activity)
    return activity_json(activity)


@router.delete("/{activity_id}")
def delete_activity(activity_id: int, current: Member = Depends(get_current_member), db: Session = Depends(get_db)):
    """
    刪除活動：僅限發起人可刪除
    - 檢查目前登入者是否為發起人（current 身分比對）
    - 非發起人刪除回傳 403
    """
    activity = activity_or_404(db, activity_id)
    if activity.organizer_id != current.id: raise HTTPException(403, "只有發起人可以刪除活動")
    db.query(models.Notification).filter_by(activity_id=activity_id).delete(synchronize_session=False)   # 先清除參照此活動的通知，避免外鍵約束阻擋刪除
    db.delete(activity); db.commit()   # 刪除活動（相關申請會因 cascade 一併刪除）
    return {"message": "活動已刪除"}


@router.post("/{activity_id}/applications", response_model=schemas.Application, status_code=201)
def apply(activity_id: int, data: schemas.ApplicationCreate, current: Member = Depends(get_current_member), db: Session = Depends(get_db)):
    """
    申請參加活動：檢查資格、防止重複申請
    - 不能申請自己建立的活動（400）
    - 活動未開放或已過截止時間不可申請（400）
    - 同一會員已申請過且未取消，不可重複申請（409）
    - 若先前曾取消，重新申請時會恢復為 pending 狀態
    - 申請人身分由登入憑證（Authorization）決定
    """
    activity = activity_or_404(db, activity_id)
    # 不能申請自己建立的活動
    if activity.organizer_id == current.id: raise HTTPException(400, "不能申請自己建立的活動")
    # 以列鎖串行化報名要求，避免並發同時報名超賣（與核准檢查一致）
    # 註：SQL Server 會編譯成 WITH (UPDLOCK, HOLDLOCK)（SQLAlchemy 的 with_for_update() 在 MSSQL 會被靜默忽略）
    activity = with_row_lock(db.query(models.Activity).filter(models.Activity.id == activity_id), models.Activity).first()
    if activity is None: raise HTTPException(404, "找不到活動")
    # 活動已停止報名或已截止（於列鎖後再檢查，確保判定以最新狀態為準）
    if activity.status != "open" or activity.deadline <= taipei_now(): raise HTTPException(400, "活動已停止報名")
    # 名額檢查：已核准人數達上限即不可再報名
    approved_count = db.query(models.Application).filter_by(activity_id=activity_id, status="approved").count()
    if approved_count >= activity.max_participants: raise HTTPException(400, "活動名額已滿")
    # 檢查是否已申請過
    existing = db.query(models.Application).filter_by(activity_id=activity_id, member_id=current.id).first()
    if existing and existing.status != "cancelled": raise HTTPException(409, "你已經申請過這個活動")
    # 若之前已取消，重新申請（更新狀態為 pending，保留原始申請時間）
    if existing:
        existing.status, existing.message = "pending", data.message
        application = existing
    else:
        application = models.Application(activity_id=activity_id, member_id=current.id, **data.model_dump()); db.add(application)
        # 建立通知給活動發起人：僅「首次申請」才通知，避免取消後重複報名造成重複通知洗版
        db.add(models.Notification(
            member_id=activity.organizer_id,
            activity_id=activity.id,
            message=f"{current.display_name} 報名了你的活動「{activity.title}」",
        ))
    db.commit(); db.refresh(application)
    return application_json(application)


@router.get("/{activity_id}/applications", response_model=List[schemas.Application])
def applications(activity_id: int, current: Member = Depends(get_current_member), db: Session = Depends(get_db)):
    """
    查看活動的申請列表：僅限發起人可查看
    - 透過目前登入身分（current）比對確認查看者為發起人，否則回傳 403
    """
    activity = activity_or_404(db, activity_id)
    if activity.organizer_id != current.id: raise HTTPException(403, "只有發起人可以查看申請")
    return [application_json(x) for x in activity.applications]


