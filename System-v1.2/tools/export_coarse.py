"""
粗评精简导出：从评分清单中提取"分数段锚点提炼"所需的最小字段集
输出: output/coarse/数学_粗评精简.json  每学科一个文件
保留: 维度得分/得分理由/评价/具体分析/原文引用/位置
剔除: 建议诊断/依据来源/理论依据/细化建议
用法: python -X utf8 export_coarse.py
"""
import json, glob, os
from collections import defaultdict
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根目录
if BASE not in sys.path:
    sys.path.insert(0, BASE)

OUT = f"{BASE}/output"
DEST = os.path.join(OUT, "coarse")
os.makedirs(DEST, exist_ok=True)

SUBJECTS = ("数学", "英语")


def norm_subject(raw):
    """标准化学科名（LLM 可能输出'人教版PEP小学英语四年级下册'这类长串）"""
    if "数学" in raw:
        return "数学"
    if "英语" in raw or "English" in raw or "PEP" in raw.upper():
        return "英语"
    if "信息" in raw or "技术" in raw or "科技" in raw:
        return "信息科技"
    return raw


def main():
    by_subject = defaultdict(list)
    for f in glob.glob(os.path.join(OUT, "competition", "*", "*_评分清单.json")):
        d = json.load(open(f, encoding="utf-8"))
        info = d.get("教案基本信息", {})
        subj = norm_subject(info.get("学科", ""))
        if subj not in SUBJECTS:
            continue
        plan = os.path.basename(os.path.dirname(f))
        by_subject[subj].append((plan, d))

    for subj, items in sorted(by_subject.items()):
        export = {"学科": subj, "标准": "competition", "教案数": len(items), "教案": []}
        for plan, d in items:
            plan_entry = {
                "教案": plan,
                "年级": d.get("教案基本信息", {}).get("年级", ""),
                "总分": d.get("评分汇总", {}).get("总分"),
                "维度": [],
            }
            for dim in d.get("维度评分", []):
                anns = [{
                    "位置": a.get("位置", ""),
                    "原文引用": a.get("原文引用", ""),
                    "评价": a.get("评价", ""),
                    "具体分析": a.get("具体分析", ""),
                } for a in dim.get("批注列表", [])]
                plan_entry["维度"].append({
                    "维度名称": dim.get("维度名称"),
                    "满分": dim.get("满分"),
                    "得分": dim.get("得分"),
                    "得分理由": dim.get("得分理由", ""),
                    "批注": anns,
                })
            export["教案"].append(plan_entry)

        out_path = os.path.join(DEST, f"{subj}_粗评精简.json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(export, fh, ensure_ascii=False, indent=2)
        print(f"✓ {subj}: {len(items)} 份 → {out_path} ({os.path.getsize(out_path)/1024:.0f}KB)")

    # 展示样例
    sample_f = glob.glob(os.path.join(DEST, "数学_粗评精简.json"))
    if sample_f:
        data = json.load(open(sample_f[0], encoding="utf-8"))
        p0 = data["教案"][0]
        d0 = p0["维度"][0]
        print("\n=== 样例：第一条维度 ===")
        print(f"教案: {p0['教案']}")
        print(f"维度: {d0['维度名称']} {d0['得分']}/{d0['满分']}")
        print(f"得分理由: {d0['得分理由'][:100]}")
        print(f"批注数: {len(d0['批注'])}")
        for a in d0["批注"][:2]:
            print(f"  原文: {a['原文引用'][:60]}")
            print(f"  评价: {a['评价']} | 分析: {a['具体分析'][:50]}")


if __name__ == "__main__":
    main()
