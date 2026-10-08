"""
增量粗评归纳：把新教案的评分结果归纳成"维度 × 档位"的共性特征，与现有锚点对比后给出建议
输出（供人工复核）：
  output/anchors/incremental_review.md    — Markdown 复核表
  output/anchors/incremental_review.json  — 结构化建议

用法：
  python tools/incremental_anchor.py 数学 "教案A.docx" "教案B.docx" ...
  python tools/incremental_anchor.py 数学 --all-new      # 归纳 output/competition 下全部（排除老教案名单）
"""
import sys, os, json, re, time
import os
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根目录
if BASE not in sys.path:
    sys.path.insert(0, BASE)
from providers import create_provider
from pipeline import load_config
from anchors import load_anchors, _band_of


OUT_DIR = f"{BASE}/output/anchors"
BANDS = ["Q1", "Q2", "Q3", "Q4"]
BAND_CN = {"Q1": "低档(0-25%)", "Q2": "中低档(25-50%)", "Q3": "中高档(50-75%)", "Q4": "高档(75-100%)"}
FIELD = 180   # 每个样本字段截断长度


def clip(t, n=FIELD):
    t = (t or "").strip().replace("\n", " ")
    return t[:n] + ("…" if len(t) > n else "")


def collect(plan_names):
    """收集样本：{(维度, 档位): [样本 dict]}"""
    groups = {}
    n_plans = 0
    for pname in plan_names:
        base = os.path.splitext(os.path.basename(pname))[0].strip()
        j = os.path.join(BASE, "output", "competition", base, f"{base}_评分清单.json")
        if not os.path.exists(j):
            print(f"  ⚠ 未找到评分清单: {base[:40]}")
            continue
        d = json.load(open(j, encoding="utf-8"))
        n_plans += 1
        for dim in d.get("维度评分", []):
            dim_name = dim.get("维度名称", "")
            band = _band_of(dim.get("得分"), dim.get("满分"))
            for a in dim.get("批注列表", []):
                groups.setdefault((dim_name, band), []).append({
                    "教案": base[:26],
                    "引用": clip(a.get("原文引用", "")),
                    "分析": clip(a.get("具体分析", "")),
                    "评价": a.get("评价", ""),
                })
    print(f"  收集 {n_plans} 份教案 → {len(groups)} 个（维度×档位）组合")
    return groups


def summarize_dim(provider, subject, dim, band_samples):
    """一次调用归纳某维度下各档位的共性特征"""
    parts = [f"学科：{subject}", f"维度：{dim}", "",
             "以下是真实教案在该维度的评审样本，已按得分档位分组（档位=该维度得分率区间）。",
             "请为每个有样本的档位归纳「共性特征」，输出 JSON：",
             '{ "Q1": {"优点":"…","缺点":"…","原文特征":"典型逻辑链；关键词：…","关键词":["…"]}, "Q2": {...} }',
             "要求：忠于样本、具体可判断、避免空话套话；某档位若无样本则不输出该键。",
             ""]
    for band in BANDS:
        items = band_samples.get(band)
        if not items:
            continue
        parts.append(f"【{band} {BAND_CN[band]}】共 {len(items)} 条样本")
        for i, s in enumerate(items[:12], 1):   # 每档最多 12 条，控制 token
            parts.append(f"{i}. [{s['教案']}] 评价={s['评价']} | 原文引用：{s['引用']} | 评审分析：{s['分析']}")
        parts.append("")
    prompt = "\n".join(parts)
    for attempt in range(3):
        try:
            raw = provider.chat_json("你是教学评价数据分析专家，擅长从真实评审样本中归纳分数段的共同特征。", prompt)
            m = re.search(r"\{[\s\S]*\}", raw)
            return json.loads(m.group(0)) if m else {}
        except Exception as e:
            print(f"    ⚠ {dim} 第{attempt+1}次失败: {str(e)[:60]}")
            time.sleep(2)
    return {}


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    subject = sys.argv[1]
    plans = sys.argv[2:]
    if plans and plans[0] == "--all-new":
        # 归纳 output/competition 下所有结果（由调用方保证是新教案）
        plans = [d for d in os.listdir(f"{BASE}/output/competition")
                 if os.path.isdir(os.path.join(BASE, "output", "competition", d))]
        print(f"--all-new：将归纳 {len(plans)} 份教案")
    elif plans and plans[0] == "--from-summary":
        # 只归纳批量脚本产出的新教案（避免混入历史教案样本）；可再附加额外教案名
        sp = plans[1] if len(plans) > 1 else f"{BASE}/output/_batch_math_summary.json"
        extra = plans[2:] if len(plans) > 2 else []
        data = json.load(open(sp, encoding="utf-8"))
        plans = [it["教案"] for it in data if it.get("总分") is not None] + extra
        print(f"--from-summary：{os.path.basename(sp)} 取 {len(plans) - len(extra)} 份"
              f"{f' + 附加 {len(extra)} 份' if extra else ''} = {len(plans)} 份")

    cfg = load_config(f"{BASE}/config.yaml")
    provider = create_provider("deepseek", cfg)
    old = load_anchors(subject) or {}

    groups = collect(plans)
    dims = sorted({d for d, _ in groups})
    print(f"涉及维度 {len(dims)} 个，开始归纳（每维度 1 次调用）...\n")

    result = {"学科": subject, "归纳教案数": len(plans), "维度": {}}
    for i, dim in enumerate(dims, 1):
        band_samples = {b: groups.get((dim, b), []) for b in BANDS}
        n_total = sum(len(v) for v in band_samples.values())
        print(f"[{i}/{len(dims)}] {dim}（样本 {n_total} 条）")
        summary = summarize_dim(provider, subject, dim, band_samples)
        if not summary:
            print("    ⚠ 归纳失败，跳过")
            continue
        # 与现有锚点对比
        old_bands = (old.get("维度", {}) or {}).get(dim, {})
        item = {"样本数": {b: len(band_samples[b]) for b in BANDS if band_samples[b]},
                "归纳": summary, "原有": {b: old_bands.get(b, {}) for b in summary}}
        # 标记：新增档位 / 更新档位
        item["状态"] = {b: ("新增" if b not in old_bands else "更新") for b in summary}
        result["维度"][dim] = item
        for b in summary:
            print(f"    {b} {item['状态'][b]}：{str(summary[b].get('缺点',''))[:50]}")

    os.makedirs(OUT_DIR, exist_ok=True)
    # 输出文件名带学科后缀，避免数学/英语互相覆盖
    suffix = "math" if subject == "数学" else "english"
    json_path = f"{OUT_DIR}/incremental_review_{suffix}.json"
    json.dump(result, open(json_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # Markdown 复核表
    md = [f"# 增量粗评归纳（{subject}）— 待复核", "",
          f"- 归纳教案数：{len(plans)}",
          f"- 涉及维度：{len(result['维度'])}",
          "- 说明：本表由新教案评审样本归纳而来，请逐条复核；确认后再更新 anchor_{}.json 与同学 Excel。".format(
              "math" if subject == "数学" else "english"), ""]
    for dim, item in result["维度"].items():
        md.append(f"## {dim}")
        md.append("")
        for b, s in item["归纳"].items():
            st = item["状态"][b]
            md.append(f"### {b} {BAND_CN[b]}（{st}）  新样本 {item['样本数'].get(b, 0)} 条")
            md.append("")
            md.append(f"- **优点**：{s.get('优点','')}")
            md.append(f"- **缺点**：{s.get('缺点','')}")
            md.append(f"- **原文特征**：{s.get('原文特征','')}")
            if s.get("关键词"):
                md.append(f"- **关键词**：{'、'.join(s['关键词'])}")
            o = item["原有"].get(b) or {}
            if o:
                md.append(f"- *原归纳*：优点={o.get('优点','')}；缺点={o.get('缺点','')}")
            md.append("")
    md_path = f"{OUT_DIR}/incremental_review_{suffix}.md"
    open(md_path, "w", encoding="utf-8").write("\n".join(md))
    print(f"\n✓ 已输出：\n  {md_path}\n  {json_path}")


if __name__ == "__main__":
    main()
