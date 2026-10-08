"""
低分候选筛选：从竞赛标准数学/英语粗评结果中，
每个维度挑出"相对低分"的前 k 名，生成给研究生人工定标的清单。
用法: python -X utf8 select_low_candidates.py [k]
输出: output/coarse/低分候选_数学.md  等
"""
import json, glob, os, sys
from collections import defaultdict
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根目录
if BASE not in sys.path:
    sys.path.insert(0, BASE)

OUT = f"{BASE}/output/coarse"
os.makedirs(OUT, exist_ok=True)
K = int(sys.argv[1]) if len(sys.argv) > 1 else 4

DIMS = ["教学内容", "教学理念", "学情分析", "教学目标", "教学资源", "教学方法",
        "过程设计", "课程思政", "课堂互动", "评价反馈", "版式观感", "文档规范"]


def norm_subject(raw):
    if "数学" in raw:
        return "数学"
    if "英语" in raw or "PEP" in raw.upper():
        return "英语"
    if "信息" in raw or "科技" in raw:
        return "信息科技"
    return raw


def load_plans():
    """返回 {subj: [{教案, 年级, 总分, dims: {维度: {得分,满分,得分理由,批注:[]}}}]}"""
    res = defaultdict(list)
    for f in glob.glob(f"{BASE}/output/competition/*/*_评分清单.json"):
        d = json.load(open(f, encoding="utf-8"))
        subj = norm_subject(d.get("教案基本信息", {}).get("学科", ""))
        if subj not in ("数学", "英语"):
            continue
        entry = {
            "教案": os.path.basename(os.path.dirname(f)),
            "年级": d.get("教案基本信息", {}).get("年级", ""),
            "总分": d.get("评分汇总", {}).get("总分"),
            "dims": {},
        }
        for x in d.get("维度评分", []):
            entry["dims"][x["维度名称"]] = {
                "得分": x.get("得分"), "满分": x.get("满分"),
                "得分理由": x.get("得分理由", ""),
                "批注": [{"位置": a.get("位置"), "原文引用": a.get("原文引用"),
                          "评价": a.get("评价"), "具体分析": a.get("具体分析")}
                         for a in x.get("批注列表", [])],
            }
        res[subj].append(entry)
    return res


def pick_lowest(plans, dim, k):
    """返回该维度得分最低的 k 个样本（分数相同时都保留，可能略多于 k）"""
    scored = []
    for p in plans:
        if dim in p["dims"]:
            scored.append((p["dims"][dim]["得分"] or 0, p))
    scored.sort(key=lambda x: x[0])
    if not scored:
        return []
    threshold = scored[min(k, len(scored)) - 1][0] if len(scored) >= k else scored[-1][0]
    picked = [(s, p) for s, p in scored if s <= threshold]
    return picked


def main():
    plans = load_plans()
    for subj, plist in sorted(plans.items()):
        lines = []
        lines.append(f"# 低分候选清单 — {subj}（competition 标准，共 {len(plist)} 份）\n")
        lines.append(f"> 每个维度取相对最低 {K} 个样本供研究生人工定标：判断其是否真正属于低分档、修正分数。\n")
        for dim in DIMS:
            picked = pick_lowest(plist, dim, K)
            if not picked:
                continue
            lines.append(f"\n## {dim}\n")
            for s, p in picked:
                d = p["dims"][dim]
                full = d["满分"]
                pct = f"{s/full*100:.0f}%" if full else "?"
                lines.append(f"- **{p['教案'][:22]}**（{p.get('年级','')}）总分{p.get('总分')} | {dim} **{s}/{full}（{pct}）**")
                lines.append(f"  - 系统得分理由：{d['得分理由'][:120]}")
                for a in d["批注"][:3]:
                    lines.append(f"  - 原文：「{a['原文引用'][:80]}」（{a.get('评价','')}）")
                lines.append("")
        path = os.path.join(OUT, f"低分候选_{subj}.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        print(f"✓ {subj}: {len(plist)} 份 → {path}")


if __name__ == "__main__":
    main()
