"""
FP-Growth 關聯規則訓練（ml/train.py）
========================================
本程式利用 MSSQL 資料庫 jiu_eat_1.2 中的 members_fake 資料表
（會員資料：興趣、居住縣市、活動類型）以 FP-Growth 演算法訓練
「會員特徵 → 活動類型」的關聯規則模型：

- 前項（antecedent）：會員的「興趣」或「居住縣市」
- 後項（consequent）：活動類型（歡唱KTV、桌遊派對、戶外運動、美食饗宴、咖啡閒聊）
- 只保留 lift >= 1 的規則（lift>1 代表該特徵對活動類型有正向關聯，
  lift=1 為中性、<1 為負向，故省略以避免誤導推薦）

訓練完成後，會將規則輸出到
    backend/services/recommendation_service.py
的 FP_RULES 常數（格式：{ 活動類型: { 會員特徵: confidence } }），
供會員登入首頁時依「興趣 + 居住縣市」推薦活動使用。

執行方式：
    python ml/train.py
"""

import math
import os
from collections import defaultdict

import pyodbc

# 路徑設定（相對於本檔案的專案根目錄）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(BASE_DIR, "backend", "services", "recommendation_service.py")

# MSSQL 資料庫連線設定（與 backend/database.py 一致的 jiu_eat_1.2）
DB_TABLE = "members_fake"
DB_CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost,1433;DATABASE=jiu_eat_1.2;Trusted_Connection=yes;"
)

# 模型參數
MIN_SUPPORT = 0.05   # 最小支持度（出現在多少比例會員的項目組合才納入）
MIN_LIFT = 1.0       # 最小提升度（只保留 lift >= 1 的規則）

# 活動類型欄位（後項）
ACTIVITY_COLS = ["歡唱KTV", "桌遊派對", "戶外運動", "美食饗宴", "咖啡閒聊"]
# 居住縣市欄位
CITY_COLS = ["新北市", "桃園市", "台中市", "台北市", "高雄市", "台南市"]


# ── 資料讀取 ──────────────────────────────────────────────
def load_members() -> list[set]:
    """
    讀取 MSSQL 資料庫 jiu_eat_1.2 的 members_fake 資料表，
    將每位會員轉成一筆交易（transaction）
    - 交易內容 = 該會員「有勾選」的興趣 + 居住縣市 + 活動類型
    - 值為 1 代表會員具備該項目
    """
    conn = pyodbc.connect(DB_CONN_STR)
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM [{DB_TABLE}]")
    columns = [desc[0] for desc in cursor.description]
    transactions = []
    rows = cursor.fetchall()
    for row in rows:
        items = set()
        for col, val in zip(columns, row):
            if col == "會員編號":
                continue
            if str(val).strip() == "1":
                items.add(str(col).strip())
        transactions.append(items)
    cursor.close()
    conn.close()
    return transactions


# ── FP-Growth：FP-Tree 節點 ──────────────────────────────
class FPNode:
    """FP-Tree 節點：item 項目、count 計數、parent 父節點、children 子節點"""
    __slots__ = ("item", "count", "parent", "children", "next")

    def __init__(self, item, count=1, parent=None):
        self.item = item
        self.count = count
        self.parent = parent
        self.children = {}
        self.next = None  # 指向下一個相同 item 的節點（形成 header table 鏈結）


def build_fp_tree(transactions: list[set], header: dict):
    """
    建立 FP-Tree（header table 已先依支援度排序並過濾）
    - transactions：所有會員交易
    - header：{ item: 該項目支援度 }，只含支援度 >= min_support 的項目
    """
    root = FPNode(None, 0, None)
    for transaction in transactions:
        # 只保留在 header 中的項目，依支援度排序後插入
        filtered = sorted(
            (item for item in transaction if item in header),
            key=lambda item: (-header[item], item),
        )
        cur = root
        for item in filtered:
            if item not in cur.children:
                cur.children[item] = FPNode(item, 0, cur)
            cur = cur.children[item]
            cur.count += 1
    # 建立 header table 的節點鏈結
    for item in header:
        _link_nodes(root, item)
    return root


def _link_nodes(node: FPNode, item: str):
    """以 node.next 串起整棵樹中相同 item 的節點（供條件樣式基使用）"""
    prev = None
    stack = [node]
    while stack:
        cur = stack.pop()
        for child in cur.children.values():
            if child.item == item:
                if prev:
                    prev.next = child
                prev = child
            stack.append(child)


def fp_growth(transactions: list[set], min_support: float) -> dict[tuple, int]:
    """
    使用 FP-Growth 找出所有頻繁項目集（含單項）
    回傳 { frozenset(項目組合): 支援度次數 }
    """
    n = len(transactions)
    threshold = math.ceil(min_support * n)
    # 第一次掃描：統計單項支援度
    item_count = defaultdict(int)
    for t in transactions:
        for item in t:
            item_count[item] += 1
    header = {item: c for item, c in item_count.items() if c >= threshold}
    if not header:
        return {}

    frequent = {}
    root = build_fp_tree(transactions, header)

    def _mine(prefix: frozenset, tree_root: FPNode, header_items: dict):
        # 依支援度由低到高處理每個項目（FP-Growth 標準做法）
        for item in sorted(header_items, key=lambda i: (header_items[i], i)):
            support = header_items[item]
            if support < threshold:
                continue
            new_prefix = prefix | frozenset({item})
            frequent[new_prefix] = support
            # 建立條件樣式基（conditional pattern base）
            cond_base = []
            node = _find_node(tree_root, item)
            while node:
                path = []
                cur = node.parent
                while cur and cur.item is not None:
                    path.append(cur.item)
                    cur = cur.parent
                if path:
                    cond_base.append((path, node.count))
                node = node.next
            # 依條件樣式基建立條件 FP-Tree
            cond_count = defaultdict(int)
            for path, cnt in cond_base:
                for p in path:
                    cond_count[p] += cnt
            cond_header = {p: c for p, c in cond_count.items() if c >= threshold}
            if not cond_header:
                continue
            cond_root = FPNode(None, 0, None)
            for path, cnt in cond_base:
                filtered = sorted(
                    (p for p in path if p in cond_header),
                    key=lambda p: (-cond_header[p], p),
                )
                cur = cond_root
                for p in filtered:
                    if p not in cur.children:
                        cur.children[p] = FPNode(p, 0, cur)
                    cur = cur.children[p]
                    cur.count += cnt
            for p in cond_header:
                _link_nodes(cond_root, p)
            _mine(new_prefix, cond_root, cond_header)

    _mine(frozenset(), root, header)
    return frequent


def _find_node(tree_root: FPNode, item: str):
    """
    回傳以 node.next 串起之鏈結的「頭」節點。
    - 需與 _link_nodes 建立鏈結的順序一致（先掃描父節點的子節點，再深入）；
      若只是依 DFS 回傳第一個 item 相符的節點，可能因 pop 順序與鏈結建立順序不同，
      回傳到鏈結中段，導致條件樣式基（path, count）漏掉鏈節頭之前的交易。
    """
    stack = [tree_root]
    while stack:
        cur = stack.pop()
        for child in cur.children.values():
            if child.item == item:
                return child
            stack.append(child)
    return None


# ── 關聯規則 ──────────────────────────────────────────────
def generate_rules(
    frequent: dict[frozenset, int], n: int, item_count: dict, min_lift: float
) -> list[dict]:
    """
    從頻繁項目集產生關聯規則
    - 前提（antecedent）：單一「會員特徵」（興趣或居住縣市）
    - 結論（consequent）：單一「活動類型」
    - confidence = support(前提∪結論) / support(前提)
    - lift = confidence / support(結論)
    - 只保留 lift >= 1 的規則
    回傳 [{category, feature, confidence, lift}]
    """
    rules = []
    for itemset, sup in frequent.items():
        if len(itemset) != 2:
            continue
        it = list(itemset)
        # 找出哪個是活動類型、哪個是會員特徵
        if it[0] in ACTIVITY_COLS and it[1] not in ACTIVITY_COLS:
            category, feature = it[0], it[1]
        elif it[1] in ACTIVITY_COLS and it[0] not in ACTIVITY_COLS:
            category, feature = it[1], it[0]
        else:
            continue
        if feature in CITY_COLS or feature in _INTERESTS:
            conf = sup / item_count[feature]
            lift = conf / (item_count[category] / n)
            if lift >= min_lift:
                rules.append(
                    {"category": category, "feature": feature,
                     "confidence": conf, "lift": lift}
                )
    return rules


# 程式開始時填入的興趣欄位（供 generate_rules 判斷特徵）
_INTERESTS = set()


# ── 輸出到 recommendation_service.py ─────────────────────
def format_fp_rules(rules: list[dict]) -> str:
    """將規則格式化成 FP_RULES 的 Python 常數內容"""
    by_cat = defaultdict(list)
    for r in rules:
        by_cat[r["category"]].append(r)
    # 分類排序：規則數量多者在前，再依分類名稱排序，讓輸出穩定
    cat_order = sorted(
        by_cat.keys(),
        key=lambda c: (-len(by_cat[c]), c),
    )
    lines = ["FP_RULES = {"]
    for cat in cat_order:
        cat_rules = sorted(by_cat[cat], key=lambda r: (-r["confidence"], r["feature"]))
        lines.append(f"    {cat!r}: {{")
        for r in cat_rules:
            lines.append(
                f"        {r['feature']!r}: {r['confidence']:.3f},  # lift={r['lift']:.3f}"
            )
        lines.append("    },")
    lines.append("}")
    return "\n".join(lines)


def write_rules_to_service(rules: list[dict], output_path: str):
    """
    將 FP_RULES 寫回 backend/services/recommendation_service.py
    - 以正規表達式定位現有的 FP_RULES = { ... } 區塊並替換
    - 其餘程式碼維持不變
    - 若檔案中尚無 FP_RULES 區塊，則直接附加在檔案尾端
    """
    with open(output_path, encoding="utf-8") as f:
        content = f.read()
    block = format_fp_rules(rules)
    marker = "FP_RULES = {"
    if marker in content:
        start = content.index(marker)
        try:
            # 找區塊結束：從 FP_RULES = { 到第一個縮排為 0 的 "}"（不含結尾註解）
            end = content.index("\n}\n", start) + len("\n}\n")
        except ValueError:
            # 區塊為空或內聯（例如 FP_RULES = {}）時不算錯誤，直接替換到第一個 "}"
            end = content.index("}", start) + 1
        new_content = content[:start] + block + "\n" + content[end:]
    else:
        new_content = content + "\n\n" + block + "\n"
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        f.write(new_content)


def main():
    transactions = load_members()
    n = len(transactions)

    # 收集所有非活動類型、非縣市的欄位作為興趣
    global _INTERESTS
    for t in transactions:
        _INTERESTS.update(t - set(ACTIVITY_COLS) - set(CITY_COLS))

    # 統計單項支援度
    item_count = defaultdict(int)
    for t in transactions:
        for item in t:
            item_count[item] += 1

    frequent = fp_growth(transactions, MIN_SUPPORT)
    rules = generate_rules(frequent, n, item_count, MIN_LIFT)
    rules.sort(key=lambda r: (-r["confidence"], r["category"], r["feature"]))

    print(f"會員數：{n}")
    print(f"頻繁項目集數目：{len(frequent)}")
    print(f"關聯規則數目（lift >= {MIN_LIFT}）：{len(rules)}")
    from collections import Counter
    counts = Counter(r["category"] for r in rules)
    for cat, cnt in counts.most_common():
        print(f"  {cat}: {cnt} 條規則")

    write_rules_to_service(rules, OUTPUT_PATH)
    print(f"\n已將 FP_RULES 寫入：{OUTPUT_PATH}")


if __name__ == "__main__":
    main()
