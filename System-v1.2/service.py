"""
============================================================
服务层（Service Layer）
供 CLI（pipeline.py）与 Web 界面（web/app.py）共用的评分流程。

设计约定：
- 不 print（进度通过 progress 回调上报）
- 不 sys.exit（异常通过 AnnotationError 向上抛）
- 产物路径与历史版本一致：output/{criteria}/{教案名}/
============================================================
"""

import os
import re
import json
import time
from typing import Callable, Dict, List, Optional

from providers import create_provider
from parsers import (
    parse_document, parse_example, scan_examples,
    list_available_plans, list_available_criteria,
    match_criteria_file, detect_subject,
    check_ocr_ready, is_scanned_pdf, ocr_available,
)
from prompts import build_user_prompt, get_prompt_variant, DIMS_BY_CRITERIA
from anchors import build_score_anchor_block, get_anchor_stats
from annotator import generate_docx, generate_json, generate_markdown
from pdf_annotator import generate_annotated_pdf
from docx_annotator import generate_annotated_docx
from suggester import generate_suggestions


class AnnotationError(RuntimeError):
    """评分流程可预期的错误（文件缺失、API 失败等）"""


CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


# ============================================================
# JSON 容错解析（含 key 空白清洗）
# ============================================================

def _clean_keys(obj):
    """递归去除 dict key 中的空白字符（LLM 可能输出'维 度名称'）"""
    if isinstance(obj, dict):
        return {k.replace(" ", "").replace("\u3000", "").replace("\t", ""): _clean_keys(v)
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_keys(x) for x in obj]
    return obj


def _unwrap_wrapper(result):
    """
    剥离 LLM 偶发的外层包装，例如：
      {"type": "json_object", "content": "{真实评分 JSON}"}
      {"choices": [{"message": {"content": "{...}"}}]}
    返回内层真实结果（找不到内层时原样返回）。
    """
    if not isinstance(result, dict):
        return result

    def try_parse_inner(text):
        if not isinstance(text, str) or not text.strip():
            return None
        for loader in (lambda s: json.loads(s),
                       lambda s: json.loads(re.search(r"\{[\s\S]*\}", s).group(0))):
            try:
                got = loader(text)
                if isinstance(got, dict):
                    return got
            except Exception:
                continue
        return None

    # 形式 1：{"type": ..., "content": "<json 字符串>"}
    inner = try_parse_inner(result.get("content"))
    if inner is not None and ("维度评分" in inner or "评分汇总" in inner or "教案基本信息" in inner):
        merged = {k: v for k, v in result.items() if k not in ("content", "type")}
        merged.update(inner)
        return merged

    # 形式 2：{"choices": [{"message": {"content": "<json 字符串>"}}]}
    try:
        inner = try_parse_inner(result["choices"][0]["message"]["content"])
        if inner is not None:
            return inner
    except Exception:
        pass

    return result


def safe_parse_json(raw: str) -> dict:
    """多层容错 JSON 解析（含 wrapper 剥离与结果完整性校验）"""
    raw = raw.replace("\uff0c", ",")  # 中文逗号 → 英文逗号
    result = None
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        pass
    if result is None:
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
        if m:
            try:
                result = json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    if result is None:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                result = json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    if result is None:
        return {"parse_error": True, "raw_text": raw}

    # 剥离可能的外层包装（2026-09-21：模型偶发返回 {"type":..,"content":"{...}"}，
    # 此前会被当作结果 → 静默产生空结果且不触发重试）
    result = _unwrap_wrapper(result)
    result = _clean_keys(result)

    # 结果完整性校验：必须有非空的"维度评分"，否则视为解析失败以触发重试
    if not isinstance(result, dict) or not result.get("维度评分"):
        return {"parse_error": True, "raw_text": raw, "reason": "维度评分为空"}

    return result


# ============================================================
# 资源清单（供 Web 首页 / 评分页下拉使用）
# ============================================================

def list_resources(base_dir: str, config: Dict) -> Dict:
    """列出可用的教案 / 标准 / 示例 / 知识库状态"""
    data = config.get("data", {})
    pl_dir = os.path.join(base_dir, data.get("plans_dir", "./data/plans"))
    cr_dir = os.path.join(base_dir, data.get("criteria_dir", "./data/criteria"))
    ex_dir = os.path.join(base_dir, data.get("examples_dir", "./data/examples"))
    return {
        "plans": list_available_plans(pl_dir),
        "criteria": list_available_criteria(cr_dir),
        "examples": [os.path.basename(e) for e in scan_examples(ex_dir)],
        "anchors": get_anchor_stats(),
    }


def resolve_plan_path(base_dir: str, config: Dict, plan_filename: str) -> str:
    """按文件名（支持部分匹配）定位教案，找不到抛错"""
    data = config.get("data", {})
    pl_dir = os.path.join(base_dir, data.get("plans_dir", "./data/plans"))
    plan_path = os.path.join(pl_dir, plan_filename)
    if os.path.exists(plan_path):
        return plan_path
    plans = list_available_plans(pl_dir)
    matches = [p for p in plans if plan_filename in p]
    if len(matches) == 1:
        return os.path.join(pl_dir, matches[0])
    raise AnnotationError(
        f"未找到教案: {plan_filename}" +
        (f"（可能的匹配: {matches}）" if matches else f"（可用教案: {plans}）")
    )


def parse_grade(plan_filename: str, plan_text: str):
    """从文件名/正文前部提取年级（返回 (年级数字, 匹配文本)）"""
    source = plan_filename + plan_text[:300]
    m = re.search(r"([一二三四五六七八九\d]+)年", source)
    if not m:
        return None, ""
    raw = m.group(1)
    grade = CN_DIGITS.get(raw) or (int(raw) if raw.isdigit() else None)
    return grade, m.group(0)


# ============================================================
# 主流程：单份教案评分
# ============================================================

def apply_grades_and_tree(result: dict) -> dict:
    """
    评分结果后处理（2026-10-04）：
      1. 按学生标准的分值区间，为每个维度标注「等级」A/B/C（由该维度得分换算）；
      2. 为每条批注写入「评价」= 所属维度等级（**替代原五档**：优秀/达标/基本达标/部分达标/未达标）；
      3. 以十二个二级维度得分重新计算总分与「各维度得分」，避免模型汇总算术误差；
      4. 在「评分汇总」中生成「一级维度汇总」（按学生标准的一级维度归并二级维度）。
    """
    from standards import score_to_grade, group_by_level1

    dims = result.get("维度评分", []) or []
    for dim in dims:
        grade = score_to_grade(dim.get("满分"), dim.get("得分"))
        dim["等级"] = grade
        for a in (dim.get("批注列表", []) or []):
            if grade:
                a["评价"] = grade        # 批注等级 = 其所属维度等级（A/B/C）

    summary = result.setdefault("评分汇总", {})
    if dims:
        # 总分属于可确定的派生值，不应继续信任模型自行求和。
        total = 0.0
        score_map = {}
        for dim in dims:
            name = dim.get("维度名称", "")
            try:
                score = float(dim.get("得分") or 0)
            except (TypeError, ValueError):
                score = 0.0
            total += score
            if name:
                score_map[name] = score
        summary["总分"] = round(total, 1)
        summary["各维度得分"] = score_map

        # 一级维度只做归组展示（不评等级），其下二级维度保留 A/B/C
        summary["一级维度汇总"] = [
            {
                "一级维度": g["一级维度"],
                "满分": g["满分"],
                "得分": g["得分"],
                "二级维度": [
                    {"维度名称": d.get("维度名称"), "满分": d.get("满分"),
                     "得分": d.get("得分"), "等级": d.get("等级", "")}
                    for d in g["维度列表"]
                ],
            }
            for g in group_by_level1(dims)
        ]
    return result


def run_annotation(
    base_dir: str,
    config: Dict,
    plan_filename: str,
    criteria_type: str = "competition",
    variant: str = "default",
    suggest: bool = False,
    dry_run: bool = False,
    progress: Optional[Callable[[str], None]] = None,
) -> Dict:
    """
    执行单份教案批注（评分 + 可选建议 + 产物生成）。

    返回: {
      "result": 评分结果 dict（dry_run 时为 None）,
      "out_dir": 产物目录,
      "subject": 学科,
      "grade": 年级,
      "plan_name": 教案名,
      "elapsed": 耗时秒,
      "files": {产物类型: 路径}
    }
    """
    def log(msg: str):
        if progress:
            progress(msg)

    t_start = time.time()
    data = config.get("data", {})
    prompt_cfg = config.get("prompt", {})
    output_dir = os.path.join(base_dir, config.get("output", {}).get("dir", "./output"))
    ex_dir = os.path.join(base_dir, data.get("examples_dir", "./data/examples"))
    cr_dir = os.path.join(base_dir, data.get("criteria_dir", "./data/criteria"))

    # === 定位教案 ===
    log(f"定位教案: {plan_filename}")
    plan_path = resolve_plan_path(base_dir, config, plan_filename)

    # === 前置检查：扫描版 PDF 且未安装 OCR 组件 → 给出友好说明（不抛技术性报错）===
    _ocr_ok, _ocr_msg = check_ocr_ready(plan_path)
    if not _ocr_ok:
        raise AnnotationError(_ocr_msg)

    plan_text = parse_document(plan_path)
    if not plan_text.strip():
        raise AnnotationError("教案解析结果为空（可能是加密或损坏的文件）")

    # === 匹配评分标准 ===
    target_criteria = match_criteria_file(plan_filename, criteria_type, cr_dir, plan_text)
    if not target_criteria:
        raise AnnotationError(
            f"未找到类型为 '{criteria_type}' 的评分标准文件，"
            f"请将标准文件放入 data/criteria/ 并在文件名中包含 competition 或 student"
        )
    matched_name = os.path.basename(target_criteria)
    subject = detect_subject(filename=plan_filename, content=plan_text) or ""
    log(f"学科检测: {subject or '未识别'} → {matched_name}")

    # === 加载标注示例 ===
    example_dirs = scan_examples(ex_dir)
    max_ex = prompt_cfg.get("max_examples", 2)
    examples = []
    for ed in example_dirs[:max_ex]:
        try:
            examples.append(parse_example(ed))
            log(f"加载示例: {os.path.basename(ed)}")
        except Exception as e:
            log(f"跳过示例 {os.path.basename(ed)}: {e}")
    if not examples:
        log("未找到标注示例，将以纯标准模式运行（无 few-shot）")

    # === 课标对照 ===
    from standards import query_standards, format_standards_for_prompt
    grade_num, grade_label = parse_grade(plan_filename, plan_text)
    standards = query_standards(subject, grade_num)
    standards_text = format_standards_for_prompt(standards)
    if standards_text:
        log(f"课标对照: {len(standards)} 条（学段: {grade_label}）")

    # === 构建提示词 ===
    criteria_text = parse_document(target_criteria)
    variant_data = get_prompt_variant(variant)
    system_prompt = variant_data["system"]
    dims = DIMS_BY_CRITERIA.get(criteria_type, DIMS_BY_CRITERIA["competition"])

    anchor_cfg = config.get("anchors", {}) or {}
    anchor_text = ""
    if anchor_cfg.get("enabled", True) and anchor_cfg.get("mode", "both") in ("score", "both"):
        anchor_text = build_score_anchor_block(subject, dims)
        if anchor_text:
            log(f"锚点注入: 档位判断标准 {len(anchor_text)} 字")

    user_prompt = build_user_prompt(
        examples=examples,
        criteria_text=criteria_text,
        criteria_name=criteria_type,
        plan_text=plan_text,
        plan_filename=plan_filename,
        max_examples=max_ex,
        standards_text=standards_text,
        dims=dims,
        anchor_text=anchor_text,
    )
    log(f"提示词构建完成: system={len(system_prompt)} 字, user={len(user_prompt)} 字")

    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "debug_prompt.txt"), "w", encoding="utf-8") as f:
        f.write(f"=== SYSTEM ===\n{system_prompt}\n\n=== USER ===\n{user_prompt}")

    # base_name 取纯文件名（上传文件形如 "uploads/xxx.pdf"，需去掉目录前缀，
    # 否则产物会落到 output/<标准>/uploads/xxx/uploads/ 的嵌套目录中）
    base_name = os.path.splitext(os.path.basename(plan_filename))[0].strip()
    plan_out = os.path.join(output_dir, criteria_type, base_name)

    if dry_run:
        log("Dry Run：提示词已保存，跳过 LLM 调用")
        return {"result": None, "out_dir": plan_out, "subject": subject,
                "grade": grade_num, "plan_name": plan_filename,
                "elapsed": time.time() - t_start, "files": {}}

    # === 调用 LLM（空输出 / 解析失败自动重试）===
    provider_name = config["llm"]["provider"]
    model_name = config["llm"].get("model", "")
    log(f"调用 LLM: {provider_name}/{model_name}")
    provider = create_provider(provider_name, config)
    raw = ""
    max_retry = 3
    for attempt in range(1, max_retry + 1):
        try:
            raw = provider.chat_json(system_prompt, user_prompt) or ""
            if len(raw.strip()) > 50:
                log(f"LLM 返回 {len(raw)} 字（第 {attempt} 次）")
                break
            log(f"第 {attempt} 次返回空输出，重试中…")
        except Exception as e:
            log(f"第 {attempt} 次调用失败: {e}，重试中…")
        if attempt < max_retry:
            time.sleep(3)
        raw = ""
    if len(raw.strip()) <= 50:
        raise AnnotationError("API 连续多次返回空内容，请检查网络或 API Key")

    with open(os.path.join(output_dir, "debug_raw_output.txt"), "w", encoding="utf-8") as f:
        f.write(raw)

    result = safe_parse_json(raw)
    if result.get("parse_error"):
        log("JSON 解析失败，重试一次…")
        for attempt in range(2, 4):
            time.sleep(3)
            try:
                raw = provider.chat_json(system_prompt, user_prompt) or ""
            except Exception as e:
                log(f"重试调用失败: {e}")
                continue
            if len(raw.strip()) > 50:
                result = safe_parse_json(raw)
                if not result.get("parse_error"):
                    log("重试成功")
                    break
        if result.get("parse_error"):
            raise AnnotationError("JSON 解析失败（模型输出格式异常），详情见 output/debug_raw_output.txt")
        with open(os.path.join(output_dir, "debug_raw_output.txt"), "w", encoding="utf-8") as f:
            f.write(raw)

    # === 等级标注（A/B/C）+ 一级维度汇总 ===
    result = apply_grades_and_tree(result)

    dim_max = sum(d.get("满分", 0) for d in result.get("维度评分", []))
    score = result.get("评分汇总", {}).get("总分", "?")
    ann_count = sum(len(d.get("批注列表", [])) for d in result.get("维度评分", []))
    log(f"评分完成: {score}/{dim_max or 100}，批注 {ann_count} 条")

    # === 生成改进建议（可选）===
    if suggest:
        log("生成改进建议（推理链 + 三库检索）…")
        provider = create_provider(provider_name, config)
        result = generate_suggestions(result, plan_text, provider,
                                      subject=subject, grade=grade_num)

    # === 生成产物 ===
    # 兜底校验：结果为空时不写产物，直接报错（避免静默产出空结果文件）
    if not result.get("维度评分"):
        raise AnnotationError(
            "评分结果为空（维度评分缺失），已中止产物生成。"
            "请重试；如反复出现，请查看 output/debug_raw_output.txt 中的模型原始输出。"
        )

    # 逐个生成，单个产物失败不阻断整体流程（保证评分结果可用）
    os.makedirs(plan_out, exist_ok=True)
    files = {}

    artifacts = [
        ("docx", f"{base_name}_批注报告.docx", lambda p: generate_docx(result, p)),
        ("json", f"{base_name}_评分清单.json", lambda p: generate_json(result, p)),
        ("md", f"{base_name}_评分清单.md", lambda p: generate_markdown(result, p)),
    ]
    # "已批注 PDF" 仅支持 PDF 教案；DOCX 教案改用「已批注 Word」（Word 原生批注气泡）
    if str(plan_path).lower().endswith(".pdf"):
        artifacts.append(("pdf", f"{base_name}_已批注.pdf",
                          lambda p: generate_annotated_pdf(plan_path, result, p)))
    elif str(plan_path).lower().endswith(".docx"):
        artifacts.append(("docx_annotated", f"{base_name}_已批注.docx",
                          lambda p: generate_annotated_docx(plan_path, result, p)))

    for key, fname, gen in artifacts:
        try:
            out = gen(os.path.join(plan_out, fname))
            if out:
                files[key] = out
        except Exception as e:
            log(f"⚠ 产物生成失败（{key}）：{e}")

    log(f"产物已生成到 {plan_out}")

    return {
        "result": result,
        "out_dir": plan_out,
        "subject": subject,
        "grade": grade_num,
        "plan_name": plan_filename,
        "elapsed": time.time() - t_start,
        "files": {k: v for k, v in files.items() if v},
    }


def run_batch(
    base_dir: str,
    config: Dict,
    criteria_type: str = "competition",
    variant: str = "default",
    suggest: bool = False,
    progress: Optional[Callable[[str], None]] = None,
) -> List[Dict]:
    """批量评分（返回成功的结果列表）"""
    results = []
    data = config.get("data", {})
    pl_dir = os.path.join(base_dir, data.get("plans_dir", "./data/plans"))
    plans = list_available_plans(pl_dir)
    for i, plan in enumerate(plans, 1):
        if progress:
            progress(f"[{i}/{len(plans)}] {plan}")
        try:
            r = run_annotation(base_dir, config, plan, criteria_type, variant,
                               suggest=suggest, progress=progress)
            results.append(r)
        except AnnotationError as e:
            if progress:
                progress(f"跳过 {plan}: {e}")
        if i < len(plans):
            time.sleep(2)
    return results
