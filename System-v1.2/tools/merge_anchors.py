"""
把增量归纳结果合并进锚点库（anchor_math.json / anchor_english.json）

合并规则：
  - 新增档位（原库没有）→ 直接写入 优点/缺点/原文特征/关键词/样本数/来源
  - 已有档位 → 更新 优点/缺点/原文特征（新归纳样本更多、更具体），
              保留人工的「模板示例」，原归纳存入「原有归纳」以便追溯
  - 同时规范化字段名（清理 "优 点" 这类带空格的脏 key）
  - 「总分画像」等其他字段保持不变

用法: python tools/merge_anchors.py [math|english]   # 缺省两者都合并
"""
import json
import os
import sys
import datetime
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根目录
if BASE not in sys.path:
    sys.path.insert(0, BASE)

ANCHOR_DIR = f"{BASE}/output/anchors"
TODAY = datetime.date.today().strftime("%Y-%m-%d")
FIELDS = ("优点", "缺点", "原文特征")


def norm_key(k: str) -> str:
    """规范化字段名：去掉空白（'优 点' → '优点'）"""
    return k.replace(" ", "").replace("\u3000", "").strip()


def build_raw(adv: str, dis: str, feat: str) -> str:
    return f"共性特征：\n优点：{adv}\n缺点：{dis}\n原文特征：{feat}"


def merge(suffix: str, subject: str) -> None:
    anchor_path = f"{ANCHOR_DIR}/anchor_{suffix}.json"
    inc_path = f"{ANCHOR_DIR}/incremental_review_{suffix}.json"
    if not (os.path.exists(anchor_path) and os.path.exists(inc_path)):
        print(f"⚠ 跳过 {suffix}：缺少文件")
        return

    anchor = json.load(open(anchor_path, encoding="utf-8"))
    inc = json.load(open(inc_path, encoding="utf-8"))
    dims = anchor.setdefault("维度", {})

    stat = {"新增": 0, "更新": 0, "保留模板": 0, "维度新增": 0}
    unmatched_dims = []

    for dim, item in inc["维度"].items():
        if dim not in dims:
            dims[dim] = {}
            stat["维度新增"] += 1
            unmatched_dims.append(dim)
        dim_node = dims[dim]

        for band, s in item["归纳"].items():
            old = dim_node.get(band) or {}
            # 规范化旧字段（清理带空格的 key）
            old_norm = {norm_key(k): v for k, v in old.items()}

            entry = {
                "raw": build_raw(s.get("优点", ""), s.get("缺点", ""), s.get("原文特征", "")),
                "优点": s.get("优点", ""),
                "缺点": s.get("缺点", ""),
                "原文特征": s.get("原文特征", ""),
                "关键词": s.get("关键词", []) or [],
                "样本数": item.get("样本数", {}).get(band, 0),
                "来源": f"增量归纳 {TODAY}（{inc.get('归纳教案数', '?')} 份教案样本）",
            }
            # 保留人工成果
            if old_norm.get("模板示例"):
                entry["模板示例"] = old_norm["模板示例"]
                stat["保留模板"] += 1
            # 原归纳留存（可追溯）
            if any(old_norm.get(f) for f in FIELDS):
                entry["原有归纳"] = {f: old_norm.get(f, "") for f in FIELDS}
                stat["更新"] += 1
            else:
                stat["新增"] += 1
            dim_node[band] = entry

    with open(anchor_path, "w", encoding="utf-8") as f:
        json.dump(anchor, f, ensure_ascii=False, indent=1)

    print(f"=== {subject}（{anchor_path.split('/')[-1]}）===")
    print(f"  新增档位 {stat['新增']}｜更新档位 {stat['更新']}｜保留模板示例 {stat['保留模板']}")
    if unmatched_dims:
        print(f"  新增维度: {unmatched_dims}（请检查维度名是否与标准一致）")
    n_band = sum(len(v) for v in anchor["维度"].values())
    n_tpl = sum(1 for v in anchor["维度"].values() for d in v.values() if d.get("模板示例"))
    print(f"  合并后：{len(anchor['维度'])} 个维度、{n_band} 个档位条目、{n_tpl} 个含模板示例")


if __name__ == "__main__":
    targets = sys.argv[1:] or ["math", "english"]
    for sfx in targets:
        merge(sfx, {"math": "数学", "english": "英语"}[sfx])
        print()
