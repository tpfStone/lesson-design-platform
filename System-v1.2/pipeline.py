"""
============================================================
教案智能批注系统 — Few-Shot 标注示例驱动
============================================================
核心理念：LLM 从已标注示例中学习标注思路，然后模仿标注新教案

用法:
  # 列出现有资源
  python pipeline.py --list

  # 运行批注
  python pipeline.py --plan "教案.pdf"
  python pipeline.py --plan "教案.pdf" --criteria competition
  python pipeline.py --plan "教案.pdf" --criteria student --variant v2_guided

  # 批量批注
  python pipeline.py --batch
============================================================
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

from providers import create_provider
from service import safe_parse_json
from parsers import (
    parse_document, parse_example, scan_examples,
    list_available_plans, list_available_criteria, match_criteria_file,
    detect_subject,
)
from prompts import build_user_prompt, get_prompt_variant
from annotator import generate_docx, generate_json, generate_markdown
from pdf_annotator import generate_annotated_pdf
from comparison import generate_comparison
from suggester import generate_suggestions


def load_config(config_path="config.yaml"):
    """加载 YAML 配置"""
    try:
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except ImportError:
        print("请安装 PyYAML: pip install pyyaml")
        sys.exit(1)
    except FileNotFoundError:
        print(f"配置文件 {config_path} 不存在，请检查路径")
        sys.exit(1)


# safe_parse_json / _clean_keys 统一由 service 层提供
def do_list(base_dir, config):
    """列出可用的资源"""
    print("=" * 60)
    print("  可用资源清单")
    print("=" * 60)

    data = config.get("data", {})
    ex_dir = os.path.join(base_dir, data.get("examples_dir", "./data/examples"))
    cr_dir = os.path.join(base_dir, data.get("criteria_dir", "./data/criteria"))
    pl_dir = os.path.join(base_dir, data.get("plans_dir", "./data/plans"))

    examples = scan_examples(ex_dir)
    criteria = list_available_criteria(cr_dir)
    plans = list_available_plans(pl_dir)

    print(f"\n标注示例 ({len(examples)}):")
    for e in examples:
        print(f"  - {os.path.basename(e)}")

    print(f"\n评分标准 ({len(criteria)}):")
    for c in criteria:
        print(f"  - {c}")

    print(f"\n待评教案 ({len(plans)}):")
    for p in plans:
        print(f"  - {p}")

    print("\n用法: python pipeline.py --plan '教案名' [--criteria competition|student]")


def do_annotate(base_dir, config, plan_filename, criteria_type, variant, dry_run, suggest=False):
    """执行单份教案批注（CLI 包装：调用 service 层，保留控制台输出）"""
    from service import run_annotation, AnnotationError
    try:
        out = run_annotation(
            base_dir=base_dir,
            config=config,
            plan_filename=plan_filename,
            criteria_type=criteria_type,
            variant=variant,
            suggest=suggest,
            dry_run=dry_run,
            progress=lambda m: print(f"  {m}"),
        )
    except AnnotationError as e:
        print(f"❌ {e}")
        sys.exit(1)
    return out["result"]


def do_batch(base_dir, config, criteria_type, variant, suggest=False):
    """批量批注所有待评教案"""
    data = config.get("data", {})
    pl_dir = os.path.join(base_dir, data.get("plans_dir", "./data/plans"))
    plans = list_available_plans(pl_dir)

    if not plans:
        print("❌ 没有找到待评教案")
        return

    output_dir = os.path.join(base_dir, config.get("output", {}).get("dir", "./output"))
    batch_results = []  # 收集所有结果

    print(f"批量批注 {len(plans)} 份教案...\n")
    for i, plan in enumerate(plans, 1):
        print(f"\n--- [{i}/{len(plans)}] {plan} ---")
        result = do_annotate(base_dir, config, plan, criteria_type, variant, dry_run=False, suggest=suggest)
        if result:
            batch_results.append((plan, result))
        if i < len(plans):
            time.sleep(2)  # 避免 API 限流

    print("\n✓ 批量批注完成")

    # 生成横向对比表
    if len(batch_results) >= 2:
        print("\n生成横向对比表...")
        md_path, csv_path = generate_comparison(
            batch_results, output_dir, criteria_type
        )
        print(f"  ✓ 对比表(MD): {md_path}")
        print(f"  ✓ 对比表(CSV): {csv_path}")


# ============================================================
def main():
    parser = argparse.ArgumentParser(description="教案智能批注系统")
    parser.add_argument("--list", action="store_true", help="列出现有资源")
    parser.add_argument("--plan", type=str, help="待评教案文件名")
    parser.add_argument("--batch", action="store_true", help="批量批注所有教案")
    parser.add_argument("--criteria", type=str, default=None,
                        help="评分标准类型 (competition 或 student)")
    parser.add_argument("--variant", "-v", type=str, default="default",
                        help="提示词变体 (default, v2_guided, v3_strict)")
    parser.add_argument("--config", "-c", type=str, default="config.yaml",
                        help="配置文件路径")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅构建提示词不调用 LLM")
    parser.add_argument("--suggest", action="store_true",
                        help="为未达标批注生成改进建议（调用知识库+LLM）")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, args.config)
    config = load_config(config_path)

    criteria_type = args.criteria or config.get("prompt", {}).get("default_criteria", "competition")

    if args.list:
        do_list(base_dir, config)
    elif args.batch:
        do_batch(base_dir, config, criteria_type, args.variant, suggest=args.suggest)
    elif args.plan:
        do_annotate(base_dir, config, args.plan, criteria_type, args.variant, args.dry_run, suggest=args.suggest)
    else:
        print("请指定操作: --list, --plan '文件名', 或 --batch")
        print("示例: python pipeline.py --plan '数学教案.pdf' --criteria competition")
        print("      python pipeline.py --list")
        print("      python pipeline.py --batch")


if __name__ == "__main__":
    main()
