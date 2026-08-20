"""
CSV 匯入腳本（scripts/import_csv.py）
=====================================
將 DB_csv/*.csv 依外鍵順序匯入資料庫（members → activities → applications → notifications → activity_photos）。

用法：
    uv run python scripts/import_csv.py            # 正常匯入（略過已存在的主鍵）
    uv run python scripts/import_csv.py --reset    # 先清空資料表再匯入

注意：
- 保留 CSV 內原有 id，避免破壞外鍵關聯。
- Postgres（Supabase）匯入後會自動 setval 修正序列，
  否則之後用 API 新增資料會主鍵衝突。
- members_fake.csv 為 ML 訓練用假資料，預設不匯入；
  需要時可先手動建表後再匯入。
"""

import argparse
import csv
import os
import sys
from datetime import datetime

from sqlalchemy import text

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from backend.database import SessionLocal

CSV_DIR = os.path.join(BASE_DIR, "DB_csv")

# 依外鍵依賴順序定義：檔案 → 資料表
TABLES = [
    ("members.csv", "members"),
    ("activities.csv", "activities"),
    ("applications.csv", "applications"),
    ("notifications.csv", "notifications"),
    ("activity_photos.csv", "activity_photos"),
]

TIME_FORMATS = ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S")

# 這些欄位是日期時間，空值應保留為 NULL；其餘字串欄位空值轉為空字串 ""（對應 model 的 default=""）
TIME_COLUMNS = {"created_at", "activity_date", "deadline"}


def parse_time(value):
    """解析 CSV 時間欄位（可能含或不含微秒）"""
    if not value:
        return None
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"無法解析時間格式：{value!r}")


def clean(row):
    """清理 CSV 資料列：
    - 空值：時間欄位 → None；其餘字串欄位 → ""（對應 model 的 default=""）
    - 時間欄位轉成 datetime
    """
    out = {}
    for k, v in row.items():
        v = v.strip()
        if k in TIME_COLUMNS:
            out[k] = parse_time(v)
        elif v == "":
            out[k] = "" if k != "id" else None
        else:
            out[k] = v
    return out


def reset(db):
    """依外鍵順序清空資料表（子表先刪）"""
    print("清空資料表...")
    for _, table in reversed(TABLES):
        db.execute(text(f"DELETE FROM {table}"))
    db.commit()


def fix_sequences(db):
    """修正 Postgres 序列，避免之後新增資料主鍵衝突（其他資料庫自動略過）"""
    for _, table in TABLES:
        try:
            db.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"(SELECT COALESCE(MAX(id), 1) FROM {table}))"
            ))
            print(f"  ✓ 已修正 {table} 的序列")
        except Exception:
            print(f"  - 略過 {table}（非 Postgres 或無序列）")


def import_csv(db):
    for filename, table in TABLES:
        path = os.path.join(CSV_DIR, filename)
        if not os.path.exists(path):
            print(f"  - 找不到 {filename}，略過")
            continue
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                data = clean(row)
                if data.get("id") is None:
                    continue
                exists = db.execute(
                    text(f"SELECT 1 FROM {table} WHERE id = :id"), {"id": int(data["id"])}
                ).first()
                if exists:
                    print(f"  - {table} id={data['id']} 已存在，略過")
                    continue
                cols = ", ".join(data.keys())
                placeholders = ", ".join(f":{k}" for k in data.keys())
                params = {
                    k: (int(v) if k == "id" else v) for k, v in data.items()
                }
                db.execute(
                    text(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"),
                    params,
                )
                count += 1
            db.commit()
            print(f"  ✓ {filename} → {table}：匯入 {count} 筆")
    fix_sequences(db)


def main():
    parser = argparse.ArgumentParser(description="匯入 DB_csv 到資料庫")
    parser.add_argument("--reset", action="store_true", help="先清空資料表再匯入")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.reset:
            reset(db)
        import_csv(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()