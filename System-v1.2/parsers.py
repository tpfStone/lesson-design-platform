"""
文档解析模块
支持 PDF / DOCX 教案、评分标准、以及带批注的 PDF 文本提取
支持扫描版 PDF 的 OCR 回退（EasyOCR，200DPI）
"""

import os
import re
import time
from typing import Dict, List


def parse_pdf(filepath: str) -> str:
    """解析 PDF，提取全部可见文本"""
    import fitz
    doc = fitz.open(filepath)
    text = ""
    for page in doc:
        text += page.get_text() + "\n"
    doc.close()
    return text


# ============================================================
# 扫描版 PDF 的 OCR 回退路径（复用课标构建的 EasyOCR 方案）
# ============================================================

_ocr_reader = None
_OCR_DPI = 200  # OCR 渲染分辨率（与课标 OCR 一致）


def _get_ocr_reader():
    """EasyOCR Reader 单例（初始化加载模型较慢，只做一次）"""
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        print("  初始化 OCR 引擎（首次约 10-30 秒）...")
        _ocr_reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
        print("  OCR 就绪")
    return _ocr_reader


def parse_pdf_ocr(filepath: str, dpi: int = _OCR_DPI) -> str:
    """
    扫描版 PDF OCR：每页渲染为 200DPI 图片 → EasyOCR 识别（中文+英文）。
    约 10-15 秒/页，识别结果可能有少量错字（扫描质量决定），
    但足以支撑评分流程，避免扫描版教案被跳过。
    """
    import fitz, io
    import numpy as np
    from PIL import Image

    doc = fitz.open(filepath)
    reader = _get_ocr_reader()
    parts = []
    t0 = time.time()
    total = len(doc)
    for i in range(total):
        pix = doc[i].get_pixmap(dpi=dpi)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        res = reader.readtext(np.array(img))
        page_text = "\n".join(r[1] for r in res)
        parts.append(page_text)
        elapsed = time.time() - t0
        print(f"    OCR [{i + 1}/{total}] {len(page_text)}字 ({elapsed:.0f}s)")
    doc.close()
    return "\n".join(parts)


def ocr_available() -> bool:
    """检测 OCR 组件（easyocr）是否已安装（不导入，避免加载慢）"""
    import importlib.util
    try:
        return importlib.util.find_spec("easyocr") is not None
    except Exception:
        return False


def is_scanned_pdf(filepath: str, threshold: int = 50, max_pages: int = 3) -> bool:
    """
    判断 PDF 是否为「扫描版」（无文字层）。
    只检查前 max_pages 页，取文字总长度与阈值比较 —— 开销极小。

    返回 True 表示：疑似扫描版（需要 OCR 才能评分）
    """
    if not str(filepath).lower().endswith(".pdf"):
        return False
    if not os.path.exists(filepath):
        return False
    try:
        import fitz
        doc = fitz.open(filepath)
        text = ""
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            text += page.get_text()
        doc.close()
        return len(text.strip()) < threshold
    except Exception:
        return False


def check_ocr_ready(filepath: str) -> tuple:
    """
    评分前的 OCR 前置检查（供 CLI/Web 统一调用，避免抛出技术性报错）。

    返回 (ok: bool, message: str)
      - ok=True  → 可以正常评分（不需要 OCR，或 OCR 已就绪）
      - ok=False → message 为**面向用户的友好说明**（含去哪安装、怎么用）
    """
    if not str(filepath).lower().endswith(".pdf"):
        return True, ""
    if not is_scanned_pdf(filepath):
        return True, ""
    if ocr_available():
        return True, ""
    return False, (
        "这份 PDF 是【扫描版】（整页图片、没有文字层），需要先安装 OCR 组件才能评分。\n\n"
        "安装方法（二选一）：\n"
        "  ① 双击 tools\\install_ocr.bat（自动安装，约 2GB，需 5-20 分钟）\n"
        "  ② 命令行执行：python -m pip install easyocr -i https://pypi.tuna.tsinghua.edu.cn/simple\n\n"
        "详细步骤见：docs\\OCR安装与使用说明.md\n"
        "提示：Word 教案、文字版 PDF 不需要安装，可直接评分。"
    )


def parse_document(filepath: str, ocr_fallback: bool = True) -> str:
    """
    自动识别 PDF 或 DOCX 并解析。

    参数:
      ocr_fallback: PDF 无文本层（扫描版）时自动 OCR 识别。
                    文本版 PDF 不受影响（零开销），仅扫描版才触发 OCR。
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.pdf':
        text = parse_pdf(filepath)
        if ocr_fallback and len(text.strip()) < 50:
            if not ocr_available():
                # 友好降级：不抛技术性异常，给出可操作的说明
                raise ValueError(
                    "这份 PDF 是【扫描版】（整页图片、没有文字层），需要先安装 OCR 组件才能评分。"
                    "安装方法：双击 tools\\install_ocr.bat，"
                    "或执行 python -m pip install easyocr -i https://pypi.tuna.tsinghua.edu.cn/simple。"
                    "详见 docs\\OCR安装与使用说明.md"
                )
            print("  ⚠ 检测到扫描版 PDF（无文本层），启动 OCR 识别（较慢）...")
            text = parse_pdf_ocr(filepath)
            if not text.strip():
                print("  ⚠ OCR 未能识别出文本，返回空内容")
        return text
    elif ext in ('.docx', '.doc'):
        return parse_docx(filepath)
    else:
        raise ValueError(f"不支持的文件格式: {ext}，仅支持 PDF 和 DOCX")


def parse_pdf_with_annotations(filepath: str) -> str:
    """
    解析带批注的 PDF，提取可见文本 + 批注内容（按页面组织）。

    输出格式：
      === 正文 ===
      [教案正文...]

      === 第1页批注 ===
      批注人：唐宝岑
      1. 教学内容8分：对教材地位、前后知识联系...

      === 第2页批注 ===
      ...

    这样 LLM 可以看到完整的"教案→批注"对应关系。
    """
    import fitz
    doc = fitz.open(filepath)

    result_parts = []
    result_parts.append("=== 教案正文 ===\n")
    body_text = ""
    for page in doc:
        body_text += page.get_text() + "\n"
    result_parts.append(body_text)

    # 提取批注内容
    result_parts.append("\n=== 批注内容（按页面） ===\n")
    for page in doc:
        annots = page.annots()
        if not annots:
            continue

        page_annots = []
        for a in annots:
            content = a.info.get("content", "").strip()
            if not content:
                # 也尝试 get_text
                try:
                    content = a.get_text().strip()
                except:
                    pass
            if content:
                page_annots.append(content)

        if page_annots:
            result_parts.append(f"\n--- 第{page.number + 1}页 ---\n")
            for i, text in enumerate(page_annots, 1):
                result_parts.append(f"{text}\n")

    doc.close()
    return "\n".join(result_parts)


def parse_docx(filepath: str) -> str:
    """解析 DOCX，提取段落和表格文本"""
    from docx import Document
    doc = Document(filepath)
    parts = []

    for p in doc.paragraphs:
        if p.text.strip():
            parts.append(p.text)

    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip().replace('\n', ' ') for c in row.cells]
            parts.append(" | ".join(c for c in cells if c))

    return "\n".join(parts)


def parse_example(example_dir: str) -> Dict:
    """
    解析一个标注示例目录。

    支持的目录结构:
      example_01/
        ├── plan.pdf (或 plan.docx)        ← 原始教案
        └── annotation.json                ← 标注结果（JSON，推荐）
           或 annotation.pdf (或 .docx)   ← 标注结果（PDF/DOCX，文本形式）

    返回:
      - 如果是 JSON: {"plan_text": "...", "annotation": {...结构化数据...}}
      - 如果是文本: {"plan_text": "...", "annotation": "...标注文本...", "annotation_type": "text"}
    """
    plan_file = None
    annotation_file = None
    annotation_type = None  # "json" or "text"

    for f in os.listdir(example_dir):
        full = os.path.join(example_dir, f)
        if not os.path.isfile(full):
            continue
        name = os.path.splitext(f)[0].lower()
        ext = os.path.splitext(f)[1].lower()

        if name == "plan" and ext in ('.pdf', '.docx'):
            plan_file = full
        elif name == "annotation":
            if ext == '.json':
                annotation_file = full
                annotation_type = "json"
            elif ext in ('.pdf', '.docx'):
                annotation_file = full
                annotation_type = "text"

    if not plan_file:
        raise FileNotFoundError(f"示例目录 {example_dir} 中缺少 plan.pdf/docx")
    if not annotation_file:
        raise FileNotFoundError(
            f"示例目录 {example_dir} 中缺少标注结果文件。\n"
            f"  请放入 annotation.json 或 annotation.pdf/docx"
        )

    if annotation_type == "json":
        import json
        with open(annotation_file, 'r', encoding='utf-8') as f:
            annotation = json.load(f)
        return {
            "plan_text": parse_document(plan_file),
            "annotation": annotation,
            "annotation_type": "json",
        }
    else:
        # PDF/DOCX 标注结果
        # PDF 用 parse_pdf_with_annotations 提取批注内容
        ext = os.path.splitext(annotation_file)[1].lower()
        if ext == '.pdf':
            annotation_text = parse_pdf_with_annotations(annotation_file)
        else:
            annotation_text = parse_document(annotation_file)
        return {
            "plan_text": parse_document(plan_file),
            "annotation": annotation_text,
            "annotation_type": "text",
        }


def scan_examples(examples_dir: str) -> List[str]:
    """扫描 examples 目录，返回所有示例子目录路径"""
    if not os.path.isdir(examples_dir):
        return []
    dirs = []
    for name in sorted(os.listdir(examples_dir)):
        full = os.path.join(examples_dir, name)
        if os.path.isdir(full):
            dirs.append(full)
    return dirs


def list_available_plans(plans_dir: str) -> List[str]:
    """列出待评教案目录中所有支持的文档"""
    if not os.path.isdir(plans_dir):
        return []
    files = []
    for f in os.listdir(plans_dir):
        if f.lower().endswith(('.pdf', '.docx')):
            files.append(f)
    return sorted(files)


def list_available_criteria(criteria_dir: str) -> List[str]:
    """列出评分标准目录中所有支持的文档"""
    if not os.path.isdir(criteria_dir):
        return []
    files = []
    for f in os.listdir(criteria_dir):
        if f.lower().endswith(('.pdf', '.docx')):
            files.append(f)
    return sorted(files)



# 学科关键词映射（用于匹配教案→评分标准）
SUBJECT_KEYWORDS = {
    "数学": ["数学"],
    "语文": ["语文"],
    "英语": ["英语"],
    "信息科技": ["信息科技", "信息技术"],
    "科学": ["科学"],
    "物理": ["物理"],
    "化学": ["化学"],
    "生物": ["生物"],
    "历史": ["历史"],
    "地理": ["地理"],
    "政治": ["政治", "道德与法治", "道法"],
    "音乐": ["音乐"],
    "美术": ["美术"],
    "体育": ["体育"],
}


def detect_subject(filename: str = "", content: str = "") -> str:
    """从文件名或内容中检测学科，返回学科名或空字符串。

    判定方式：**加权计分**（2026-10-04 改）
      1. 分别累加各学科的命中关键词权重，取总分最高的学科；
      2. 不再"先命中先返回"（旧逻辑下数学排在第一位且含"图形/加法"等宽泛词，
         导致英语、语文教案只要出现这类词就被误判为数学）；
      3. 同分时：先比"专有词（权重 3）"命中数，再看文件名命中，最后按固定优先级。

    权重设计：
      文件名命中        ×2（在原权重基础上加倍）
      专有词（权重 3）   如「人教版数学」「PEP」「小学数学」
      学科术语（权重 2） 如「口算」「词汇教学」「Let's talk」
      泛化词（权重 1）   如「图形」「加法」「Unit」「farm」——其他学科也会出现
    """
    scores = {}
    dedup = {}       # 记录每科的专有词命中数，用于打破平局

    def _add(subject, weight, is_strong=False):
        scores[subject] = scores.get(subject, 0) + weight
        if is_strong:
            dedup[subject] = dedup.get(subject, 0) + 1

    # ---- ① 文件名（权重 ×2）----
    if filename:
        for subject, keywords in SUBJECT_KEYWORDS.items():      # 精确学科名（数学/英语/…）
            for kw in keywords:
                if kw in filename:
                    _add(subject, 5, is_strong=True)
        for subject, kws in SUBJECT_KEYWORDS_WEIGHTED.items():  # 加权词表也扫文件名
            for kw, wt in kws:
                if kw in filename:
                    _add(subject, wt * 2, is_strong=(wt >= 3))

    # ---- ② 内容（前 2000 字，权重 ×1）----
    if content:
        head = content[:2000]
        for subject, kws in SUBJECT_KEYWORDS_WEIGHTED.items():
            for kw, wt in kws:
                if kw in head:
                    _add(subject, wt, is_strong=(wt >= 3))

        # ---- ③ 辅助信号：外文（英文）占比高 → 强化英语判定 ----
        # 仅当英语已有基础分时才加分（避免把 Python 代码多的信息科技教案误判为英语）
        if scores.get("英语", 0) > 0:
            letters = sum(1 for ch in head if ch.isascii() and ch.isalpha())
            visible = sum(1 for ch in head if not ch.isspace())
            if visible and letters / visible > 0.2:
                _add("英语", 3)

    if not scores:
        return ""

    best = max(scores.values())
    tied = [s for s, v in scores.items() if v == best]
    if len(tied) == 1:
        return tied[0]

    # 平局规则 1：专有词命中多者优先
    best_strong = max(dedup.get(s, 0) for s in tied)
    strong_tied = [s for s in tied if dedup.get(s, 0) == best_strong]
    if len(strong_tied) == 1:
        return strong_tied[0]

    # 平局规则 2：按固定优先级（数/语/英/信息…）
    for s in SUBJECT_KEYWORDS:
        if s in strong_tied:
            return s
    return strong_tied[0]


def detect_subject_detail(filename: str = "", content: str = "") -> dict:
    """调试用：返回各学科得分明细（便于排查误判原因）"""
    scores, dedup = {}, {}

    def _add(subject, weight, is_strong=False):
        scores[subject] = scores.get(subject, 0) + weight
        if is_strong:
            dedup[subject] = dedup.get(subject, 0) + 1

    if filename:
        for subject, keywords in SUBJECT_KEYWORDS.items():
            for kw in keywords:
                if kw in filename:
                    _add(subject, 5, True)
        for subject, kws in SUBJECT_KEYWORDS_WEIGHTED.items():
            for kw, wt in kws:
                if kw in filename:
                    _add(subject, wt * 2, wt >= 3)
    if content:
        head = content[:2000]
        for subject, kws in SUBJECT_KEYWORDS_WEIGHTED.items():
            for kw, wt in kws:
                if kw in head:
                    _add(subject, wt, wt >= 3)
    return {"scores": scores, "strong_hits": dedup,
            "result": detect_subject(filename, content)}


# 加权关键词表（2026-10-04 新增，用于 detect_subject 的计分判定）
SUBJECT_KEYWORDS_WEIGHTED = {
    "数学": [
        # 专有词（权重 3）
        ("人教版数学", 3), ("苏教版数学", 3), ("北师大版数学", 3), ("小学数学", 3),
        ("数学教学", 3), ("数学课", 3), ("数学广角", 3), ("数学教案", 3),
        # 学科术语（权重 2）
        ("数学", 2), ("异分母分数", 2), ("同分母分数", 2), ("分数加减", 2),
        ("几何", 2), ("代数", 2), ("口算", 2), ("笔算", 2), ("竖式", 2),
        ("加减法", 2), ("乘法口诀", 2), ("四则运算", 2), ("方程", 2),
        ("统计图", 2), ("角的度量", 2), ("周长", 2), ("面积", 2), ("体积", 2),
        # 泛化词（权重 1）——其他学科也可能出现，不可单独作为判定依据
        ("加法", 1), ("减法", 1), ("乘法", 1), ("除法", 1), ("小数", 1),
        ("分数", 1), ("图形", 1), ("数一数", 1), ("应用题", 1),
    ],
    "英语": [
        # 专有词（权重 3）
        ("人教版英语", 3), ("小学英语", 3), ("英语教学", 3), ("英语课", 3),
        ("PEP", 3), ("外研版", 3), ("译林版", 3),
        # 学科术语（权重 2）
        ("英语", 2), ("English", 2), ("词汇教学", 2), ("语法教学", 2),
        ("听说教学", 2), ("Let's talk", 2), ("Let's learn", 2),
        ("Let's do", 2), ("Look and say", 2), ("Read and write", 2),
        ("Part A", 2), ("Part B", 2), ("Part C", 2),
        ("Unit", 3),          # 英文 "Unit" 基本只出现在英语教案（中文教案写"第三单元"）
        ("story time", 2), ("Ask and answer", 2),
        # 泛化词（权重 1）
        ("farm", 1), ("weather", 1), ("listen", 1), ("word", 1),
    ],
    "语文": [
        ("人教版语文", 3), ("部编版语文", 3), ("小学语文", 3), ("语文教学", 3),
        ("语文", 2), ("识字", 2), ("阅读教学", 2), ("写作教学", 2),
        ("古诗", 1), ("文言文", 1), ("课文", 1),
    ],
    "信息科技": [
        ("信息科技", 3), ("信息技术", 3), ("编程教学", 3),
        ("编程", 2), ("算法设计", 2), ("人工智能", 2), ("计算机", 2),
        ("数据结构", 2), ("机器人", 2),
        ("Python", 1), ("scratch", 1), ("程序", 1),
    ],
}


def match_criteria_file(
    plan_filename: str,
    criteria_type: str,
    criteria_dir: str,
    plan_content: str = ""
) -> str:
    """
    根据教案学科和评分标准类型，匹配最合适的评分标准文件。

    匹配规则：
    1. 从教案文件名和内容中检测学科
    2. 在 criteria_dir 中找同时包含 criteria_type 和学科关键词的文件
    3. 如果找不到精确匹配，回退到只匹配 criteria_type 的第一个文件
    4. 如果只有一个符合条件的文件，直接返回

    返回: 匹配到的评分标准文件完整路径
    """
    all_files = list_available_criteria(criteria_dir)

    # 先筛选出类型匹配的文件（含 criteria_type 关键词）
    type_matched = [
        f for f in all_files
        if criteria_type.lower() in os.path.splitext(f)[0].lower()
    ]

    if not type_matched:
        return ""

    # 如果只有一份，直接返回
    if len(type_matched) == 1:
        return os.path.join(criteria_dir, type_matched[0])

    # 多份时尝试学科匹配（先文件名，再内容）
    subject = detect_subject(filename=plan_filename, content=plan_content)
    if subject:
        subject_matched = [
            f for f in type_matched
            if subject in f
        ]
        if subject_matched:
            return os.path.join(criteria_dir, subject_matched[0])

    # 学科匹配失败，返回第一份（并警告）
    return os.path.join(criteria_dir, type_matched[0])