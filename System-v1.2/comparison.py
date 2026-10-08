"""
============================================================
批注结果横向对比表生成
按评分标准自动分组，每组独立对比，支持 MD + CSV 双输出
============================================================
"""

import csv
import os
import re
from datetime import datetime
from collections import OrderedDict
from typing import List, Dict, Tuple


def generate_comparison(
    results: List[Tuple[str, Dict]],
    output_dir: str,
    criteria_type: str,
    criteria_name: str = ""
) -> Tuple[str, str]:
    """
    生成分组横向对比表。

    按评分标准的维度指纹自动分组，同标准一组，各自生成对比表。
    最后合成一份 MD、一份 CSV（带评分标准列）。

    返回: (md_path, csv_path)
    """
    if not results:
        print("  ⚠ 没有结果可生成对比表")
        return "", ""

    # ---- 按维度指纹分组 ----
    groups = OrderedDict()  # group_label -> [rows]

    for plan_name, r in results:
        dims = tuple(d["维度名称"] for d in r.get("维度评分", []))
        label = _make_group_label(dims, plan_name, r, criteria_type)
        if label not in groups:
            groups[label] = {"dims": list(dims), "rows": []}

        dim_scores = {d["维度名称"]: d.get("得分", 0) for d in r.get("维度评分", [])}
        total = r.get("评分汇总", {}).get("总分", "?")
        groups[label]["rows"].append({
            "name": plan_name,
            "scores": dim_scores,
            "total": total,
        })

    # ---- 生成 Markdown ----
    md_path = os.path.join(output_dir, "batch_comparison.md")
    os.makedirs(output_dir, exist_ok=True)

    md = _build_markdown_header(groups, results, criteria_type, criteria_name)
    md += "\n---\n\n"

    # 每组一节
    for label, group in groups.items():
        if len(group["rows"]) >= 1:
            md += _build_group_section(label, group)

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md)

    # ---- 生成 CSV（带评分标准列）----
    csv_path = os.path.join(output_dir, "batch_comparison.csv")
    _build_csv(groups, csv_path)

    grp_info = ", ".join(f"{label}({len(g['rows'])}份)" for label, g in groups.items())
    print(f"    分组: {grp_info}")

    return md_path, csv_path


def _make_group_label(dims: Tuple[str, ...], plan_name: str,
                      result: Dict = None, criteria_type: str = "") -> str:
    """根据维度指纹 + 教案信息生成组标签，并附标准分类。"""
    # 0. 标准类型优先从维度指纹推断（混合跑两套标准也能正确区分）
    inferred = _infer_criteria(dims)
    eff_criteria = inferred or criteria_type

    # 1. 从评分结果中提取学科信息，标准化为四类
    if result:
        info = result.get("教案基本信息", {})
        subject = info.get("学科", "").strip()
        if subject:
            # 标准化：小学数学/初中数学/高中数学 → 数学
            for std in ["数学", "语文", "英语"]:
                if std in subject:
                    return _with_criteria(std, eff_criteria)
            if "信息" in subject or "技术" in subject or "科技" in subject:
                return _with_criteria("信息科技", eff_criteria)
            return _with_criteria(subject, eff_criteria)

    # 2. 从文件名找学科
    subject_patterns = {
        "语文": "语文",
        "数学": "数学|分数|几何|代数",
        "英语": "英语|English",
        "信息科技": "信息科技|信息|Python|python|编程|算法",
        "科学": "科学",
    }
    for subj, pat in subject_patterns.items():
        if re.search(pat, plan_name):
            return _with_criteria(subj, eff_criteria)

    # 3. 从维度指纹推断
    dim_set = set(dims)
    if "课程思政" in dim_set:
        return _with_criteria("数学/语文/英语", eff_criteria)
    if "文档规范" in dim_set and len(dims) <= 8:
        return _with_criteria("信息科技", eff_criteria)

    return _with_criteria("其他", eff_criteria)


def _with_criteria(subject: str, criteria_type: str) -> str:
    """组标签附加标准分类（竞赛标准/学生标准）"""
    label = {"competition": "竞赛标准", "student": "学生标准"}.get(criteria_type, criteria_type)
    return f"{subject}（{label}）"


def _infer_criteria(dims: Tuple[str, ...]) -> str:
    """
    从维度指纹推断实际使用的评分标准类型：
    - 含"结构完整" → 学生标准（student 评价指标）
    - 含"文档规范" → 竞赛标准（田家炳杯等）
    - 均不含 → 返回空串，由调用方回退到全局 criteria_type
    """
    if "结构完整" in dims:
        return "学生标准"
    if "文档规范" in dims:
        return "竞赛标准"
    return ""


def _build_markdown_header(groups, results, criteria_type, criteria_name) -> str:
    """构建 MD 文件头（总览）"""
    label = criteria_name or criteria_type
    total_plans = len(results)
    group_count = len(groups)

    md = f"# 教案批注横向对比\n\n"
    md += f"- **评分标准类型**: {label}\n"
    md += f"- **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    md += f"- **教案总数**: {total_plans} 份  |  分组数: {group_count} 组\n\n"

    # 总览表
    md += "## 总览\n\n"
    md += "| 教案 | 学科 | 分类 | 总分 |\n"
    md += "|------|------|------|------|\n"
    for label, group in groups.items():
        subject, cat = _split_label(label)
        for row in group["rows"]:
            md += f"| {row['name']} | {subject} | {cat} | **{row['total']}** |\n"

    return md


def _split_label(label: str) -> Tuple[str, str]:
    """将组标签拆为 (学科, 分类)。形如 '数学（竞赛标准）'"""
    if "（" in label and "）" in label:
        subject = label.split("（")[0]
        cat = label.split("（")[1].rstrip("）")
        return subject, cat
    return label, ""


def _build_group_section(label: str, group: Dict) -> str:
    """构建一个分组的对比表章节"""
    rows = group["rows"]
    dims = group["dims"]

    md = f"## {label}（{len(rows)} 份）\n\n"

    # 对比表
    header = "| 教案"
    sep = "|------"
    for dim in dims:
        header += f" | {dim}"
        sep += "|------"
    header += f" | **总分** |"
    sep += f"|--------|"

    md += header + "\n" + sep + "\n"

    for row in rows:
        line = f"| {row['name']}"
        for dim in dims:
            score = row["scores"].get(dim, "-")
            line += f" | {score}"
        line += f" | **{row['total']}** |"
        md += line + "\n"

    md += "\n"

    # 只有多份教案时才显示平均分
    if len(rows) >= 2:
        md += f"### 各维度平均分\n\n"
        for dim in dims:
            scores = [r["scores"].get(dim) for r in rows if dim in r["scores"]]
            if scores:
                avg = sum(scores) / len(scores)
                md += f"- **{dim}**: {avg:.1f} 分\n"

    md += "\n---\n\n"
    return md


def _build_csv(groups: OrderedDict, csv_path: str):
    """导出 CSV，加评分标准列"""
    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)

        # 写表头：教案, 评分标准, [维度...], 总分
        # 收集所有维度（用于并集，但 CSV 不同标准分开处理）
        all_dims = []
        for group in groups.values():
            for d in group["dims"]:
                if d not in all_dims:
                    all_dims.append(d)

        header = ["教案", "评分标准"] + all_dims + ["总分"]
        writer.writerow(header)

        for label, group in groups.items():
            for row in group["rows"]:
                line = [row["name"], label]
                for dim in all_dims:
                    line.append(row["scores"].get(dim, ""))
                line.append(row["total"])
                writer.writerow(line)
