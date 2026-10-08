"""
============================================================
粗评锚点库：加载与渲染
数据来源：output/anchors/anchor_{subject}.json
（由低一级同学整理的"粗评归纳+模板示例.xlsx"解析而来）

用途：
- 评分阶段：注入"档位判断标准·简版"，校准打分尺度（治区分度不足）
- 建议阶段：注入"该维度当前档 + 相邻档"详细锚点与示例片段
============================================================
"""

import os
import json
from typing import Dict, List, Optional

_ANCHOR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "anchors")
_cache: Dict[str, Optional[Dict]] = {}

BAND_NAMES = {
    "Q1": "低档(0-25%)",
    "Q2": "中低档(25-50%)",
    "Q3": "中高档(50-75%)",
    "Q4": "高档(75-100%)",
}

# 学生标准的维度名与竞赛的标准差异（文档规范 ↔ 结构完整）
DIM_ALIAS = {"结构完整": "文档规范"}


def load_anchors(subject: str) -> Optional[Dict]:
    """加载某学科锚点库（带缓存）"""
    if subject in _cache:
        return _cache[subject]
    fname = {"数学": "anchor_math.json", "英语": "anchor_english.json"}.get(subject)
    if not fname:
        _cache[subject] = None
        return None
    path = os.path.join(_ANCHOR_DIR, fname)
    if not os.path.exists(path):
        _cache[subject] = None
        return None
    with open(path, "r", encoding="utf-8") as f:
        _cache[subject] = json.load(f)
    return _cache[subject]


def _band_of(score, full) -> str:
    """得分 → 档位（边界归高档，与粗评统计口径一致）"""
    if not full:
        return "Q3"
    r = score / full
    if r < 0.25:
        return "Q1"
    if r < 0.5:
        return "Q2"
    if r < 0.75:
        return "Q3"
    return "Q4"


def _one_line(band_data: Dict) -> str:
    """把某档数据压成一句话（用于评分阶段简版）"""
    adv = (band_data.get("优点") or "").strip().rstrip("。")
    dis = (band_data.get("缺点") or "").strip().rstrip("。")
    feat = (band_data.get("特征") or "").strip().rstrip("。")
    if adv and dis:
        return f"{adv}；但{dis}"
    return adv or dis or feat or ""


def _logic_of(band_data: Dict) -> str:
    """提取原文特征中的典型逻辑链与关键词"""
    raw = (band_data.get("原文特征") or "").strip()
    return raw


def build_score_anchor_block(subject: str, dims: List[tuple] = None) -> str:
    """
    评分阶段注入的"档位判断标准·简版"。
    dims: [(维度名, 满分), ...]；为 None 时输出锚点库中全部维度。
    """
    a = load_anchors(subject)
    if not a:
        return ""

    lines = ["## 维度档位判断参照（基于真实教案样本归纳，用于校准打分尺度）",
             "以下每档描述来自真实教案样本的共同特征，请据此判断待评教案处于哪一档，**不同档位之间应拉开分数差距**。", ""]

    dim_scores = dict(dims) if dims else {}
    dim_keys = [d for d, _ in dims] if dims else list(a.get("维度", {}).keys())

    for dim in dim_keys:
        key = DIM_ALIAS.get(dim, dim)
        bands = a.get("维度", {}).get(key)
        if not bands:
            continue
        full = dim_scores.get(dim)
        header = f"【{dim}】" + (f"满分{full}" if full else "")
        lines.append(header)
        for b in ["Q1", "Q2", "Q3", "Q4"]:
            data = bands.get(b)
            if not data:
                continue
            desc = _one_line(data)
            if desc:
                lines.append(f"- {BAND_NAMES[b]}：{desc}")
        lines.append("")

    # 总分画像（若有）
    tp = a.get("总分画像", {})
    if tp:
        lines.append("【整体画像参考】")
        for b in ["Q1", "Q2", "Q3", "Q4"]:
            data = tp.get(b)
            if not data:
                continue
            desc = _one_line(data)
            if desc:
                lines.append(f"- {BAND_NAMES[b]}：{desc}")
        lines.append("")

    return "\n".join(lines)


def build_advice_anchor_block(subject: str, dim: str, score, full,
                             include_template: bool = True,
                             template_chars: int = 260) -> str:
    """
    建议阶段注入的"该维度当前档 + 相邻档"详细锚点。
    """
    a = load_anchors(subject)
    if not a or not dim:
        return ""
    key = DIM_ALIAS.get(dim, dim)
    bands = a.get("维度", {}).get(key)
    if not bands:
        return ""

    cur = _band_of(score, full)
    order = ["Q1", "Q2", "Q3", "Q4"]
    idx = order.index(cur)
    # 相邻档：取更上一档（改进方向）
    neighbors = [cur]
    if idx + 1 < len(order) and order[idx + 1] in bands:
        neighbors.append(order[idx + 1])

    out = [f"### 该维度档位参照（{dim} 当前 {score}/{full} → {BAND_NAMES[cur]}）"]
    for b in neighbors:
        data = bands.get(b)
        if not data:
            continue
        tag = "当前档" if b == cur else "改进目标档"
        adv = (data.get("优点") or "").strip()
        dis = (data.get("缺点") or "").strip()
        logic = _logic_of(data)
        out.append(f"- **{BAND_NAMES[b]}（{tag}）**")
        if adv:
            out.append(f"  - 已达：{adv}")
        if dis:
            out.append(f"  - 典型不足：{dis}")
        if logic:
            out.append(f"  - 典型逻辑链/关键词：{logic}")
    # 当前档示例片段
    if include_template:
        tpl = (bands.get(cur, {}) or {}).get("模板示例")
        if tpl:
            snippet = tpl.strip()[:template_chars].replace("\n", " ")
            out.append(f"- **该档示例片段（节选，供写法参考）**：{snippet}…")
    return "\n".join(out)


def get_anchor_stats() -> Dict[str, Dict]:
    """锚点覆盖统计（首页展示用）"""
    stats = {}
    for subj in ("数学", "英语"):
        a = load_anchors(subj)
        if not a:
            stats[subj] = {"维度数": 0, "档位条目": 0, "含模板": 0}
            continue
        n_band = sum(len(v) for v in a.get("维度", {}).values())
        n_tpl = sum(1 for v in a.get("维度", {}).values()
                    for d in v.values() if d.get("模板示例"))
        stats[subj] = {"维度数": len(a.get("维度", {})), "档位条目": n_band, "含模板": n_tpl}
    return stats
