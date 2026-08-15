"""
推薦演算法服務（backend/services/recommendation_service.py）
============================================================
本模組實作活動推薦邏輯，採用「FP-Growth 關聯規則」計分：

- 依據 ml/train.py（FP-Growth, lift>=1）所產生的關聯規則（FP_RULES）
  （前提＝會員興趣或居住縣市，結論＝推薦活動分類），
- 比對會員已勾選的「興趣」與「居住縣市」，找出該會員最可能參加的活動分類，
- 該分類（activity.category）越貼合此推薦，分數越高，排序越前。

未來若要改用其他模型，可再替換本模組內 recommend() 的內容
（API 與前端不需更動）。
"""

from sqlalchemy.orm import Session

from .. import models
from ..common import activity_json, member_or_404, taipei_now

# ---------------------------------------------------------------
# FP-Growth 關聯規則（由 ml/train.py 依資料庫 members_fake 產生）
#   格式：{ 推薦活動分類: { 會員特徵(興趣/縣市): confidence } }
#   只保留 lift >= 1 的規則（lift>1 代表該特徵對活動分類有正向關聯，
#   lift=1 為中性、<1 為負向，故省略以避免誤導推薦）。
#   confidence 越高，代表該特徵會員越容易促成此活動分類。
# ---------------------------------------------------------------
FP_RULES = {
    '戶外運動': {
        '登山': 0.800,  # lift=1.169
        '釣魚': 0.797,  # lift=1.165
        '跑步': 0.797,  # lift=1.164
        '游泳': 0.794,  # lift=1.160
        '騎車': 0.793,  # lift=1.159
        '園藝': 0.791,  # lift=1.156
        '開車兜風': 0.787,  # lift=1.150
        '旅遊': 0.784,  # lift=1.145
        '運動': 0.777,  # lift=1.135
        '露營': 0.761,  # lift=1.112
        '打球': 0.759,  # lift=1.109
        '健身': 0.730,  # lift=1.066
        '台南市': 0.720,  # lift=1.052
        '模型': 0.708,  # lift=1.035
        '台中市': 0.701,  # lift=1.025
        '攝影': 0.698,  # lift=1.019
        '桃園市': 0.697,  # lift=1.018
        '志工': 0.695,  # lift=1.015
        '象棋': 0.693,  # lift=1.013
        '烘焙': 0.692,  # lift=1.011
    },
    '桌遊派對': {
        '程式設計': 0.733,  # lift=1.420
        '象棋': 0.719,  # lift=1.393
        'cosplay': 0.701,  # lift=1.358
        '圍棋': 0.663,  # lift=1.284
        '電玩': 0.657,  # lift=1.274
        '模型': 0.646,  # lift=1.252
        '瑜珈': 0.551,  # lift=1.069
        '新北市': 0.546,  # lift=1.058
        '打球': 0.535,  # lift=1.036
        '釣魚': 0.531,  # lift=1.030
        '寵物': 0.523,  # lift=1.014
        '繪畫': 0.522,  # lift=1.011
        '開車兜風': 0.522,  # lift=1.011
        '台北市': 0.521,  # lift=1.010
        '烘焙': 0.520,  # lift=1.008
        '高雄市': 0.520,  # lift=1.007
    },
    '咖啡閒聊': {
        '手工藝': 0.808,  # lift=1.189
        '冥想': 0.807,  # lift=1.187
        '寫作': 0.796,  # lift=1.170
        '繪畫': 0.796,  # lift=1.170
        '閱讀': 0.794,  # lift=1.168
        '志工': 0.793,  # lift=1.167
        '收藏': 0.788,  # lift=1.159
        '寵物': 0.774,  # lift=1.139
        '逛街': 0.764,  # lift=1.124
        '喝茶': 0.755,  # lift=1.111
        '書法': 0.751,  # lift=1.105
        '咖啡': 0.748,  # lift=1.099
        '新北市': 0.705,  # lift=1.037
        '台北市': 0.694,  # lift=1.020
        '象棋': 0.683,  # lift=1.005
    },
    '美食饗宴': {
        '品酒': 0.758,  # lift=1.385
        '烹飪': 0.713,  # lift=1.304
        '烘焙': 0.682,  # lift=1.246
        '喝茶': 0.665,  # lift=1.216
        '咖啡': 0.662,  # lift=1.210
        '料理研究': 0.640,  # lift=1.170
        '逛街': 0.610,  # lift=1.116
        '電玩': 0.602,  # lift=1.101
        '台北市': 0.599,  # lift=1.094
        '書法': 0.584,  # lift=1.067
        '旅遊': 0.563,  # lift=1.029
        '高雄市': 0.561,  # lift=1.026
        '模型': 0.557,  # lift=1.019
        '台南市': 0.552,  # lift=1.009
        '程式設計': 0.548,  # lift=1.003
    },
    '歡唱KTV': {
        '看劇': 0.671,  # lift=1.389
        '舞蹈': 0.662,  # lift=1.369
        '音樂': 0.659,  # lift=1.362
        '看電影': 0.644,  # lift=1.331
        '模型': 0.526,  # lift=1.088
        '志工': 0.521,  # lift=1.078
        '高雄市': 0.514,  # lift=1.064
        '釣魚': 0.512,  # lift=1.059
        '閱讀': 0.500,  # lift=1.034
        '桃園市': 0.489,  # lift=1.012
        '攝影': 0.488,  # lift=1.009
    },
}

# 評分權重
BASE_SCORE = 20            # 活動仍可報名的基礎分
INTEREST_WEIGHT = 60       # 命中的「興趣」特徵權重
CITY_WEIGHT = 40           # 命中的「居住縣市」特徵權重
LOCATION_WEIGHT = 30       # 活動位於會員居住縣市時的加成


def _norm(text: str) -> str:
    """標準化分類名稱：去除空白並轉小寫，供比對使用"""
    return (text or "").replace(" ", "").strip().lower()


def _fp_rules_for(category: str) -> dict:
    """依規範化後的分類，回傳對應的 FP 關聯規則；找不到則回傳空白"""
    cat = _norm(category)
    for key, vals in FP_RULES.items():
        if _norm(key) == cat:
            return vals
    return {}


def _norm_city(city: str) -> str:
    """把縣市名稱補上「市」尾碼，與規則中的縣市鍵一致（台北→台北市）
    - 已以「市」或「縣」結尾時原樣回傳（避免「新竹縣」被誤補成「新竹縣市」）
    """
    if not city:
        return ""
    if city.endswith("市") or city.endswith("縣"):
        return city
    return city + "市"


def recommend(member_id: int, db: Session) -> list[dict]:
    """
    依據會員資料以 FP-Growth 關聯規則產生推薦活動列表
    - 先確認會員存在（member_or_404）
    - 排除會員自己建立的、已申請的、已過截止時間或已過期的活動
    - 依會員的「興趣」與「居住縣市」命中 FP 規則，對符合分類的活動加權計分
    - 最後依分數排序回傳，分數相同時活動時間較早者優先
    """
    member = member_or_404(db, member_id)                       # 確認會員存在，否則 404
    # 收集會員已申請且未取消的活動 ID，推薦時排除這些活動
    applied_ids = {x.activity_id for x in member.applications if x.status != "cancelled"}
    # 將會員的興趣依逗號拆成集合（去除空白），用於比對 FP 規則
    interests = {x.strip() for x in member.interests.split(",") if x.strip()}
    city = (member.city or "").strip()
    norm_city = _norm_city(city)
    results = []
    for activity in db.query(models.Activity).filter_by(status="open").all():
        # 排除自己建立的、已申請的、已過截止時間的、或活動已過期的
        if activity.organizer_id == member_id or activity.id in applied_ids or activity.deadline <= taipei_now() or activity.activity_date <= taipei_now():
            continue
        # 基礎分：目前仍可報名
        score = BASE_SCORE
        reasons = ["目前仍可報名"]
        fp = _fp_rules_for(activity.category)                    # 取得此分類的 FP 規則
        fp_points = 0.0
        # 1) 命中會員的「興趣」
        for interest in interests:
            w = fp.get(interest)
            if w is not None:
                fp_points += w * INTEREST_WEIGHT
                reasons.append(f"你的興趣「{interest}」與「{activity.category}」高度相關")
        # 2) 命中會員的「居住縣市」
        if norm_city and norm_city in fp:
            fp_points += fp[norm_city] * CITY_WEIGHT
            reasons.append(f"居住「{city}」的人常參加「{activity.category}」活動")
        # 3) 活動位於會員居住縣市（距離加成）
        if city and _norm_city(city) == _norm_city(activity.city):
            fp_points += LOCATION_WEIGHT
            reasons.append("活動就在你的居住縣市")
        score += fp_points
        results.append({**activity_json(activity), "score": round(score), "reasons": reasons})
    # 依分數由高到低排序；分數相同時活動時間較早者在前
    return sorted(results, key=lambda x: (-x["score"], x["activity_date"]))