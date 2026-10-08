"""课标知识库查询模块"""
import json, os, re

KB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge_base")
_cache = {}

GRADE_TO_STAGE = {
    1: "1-2", 2: "1-2",
    3: "3-4", 4: "3-4",
    5: "5-6", 6: "5-6",
    7: "7-9", 8: "7-9", 9: "7-9",
}


def _load(subject: str) -> list:
    """加载结构化知识库"""
    if subject in _cache:
        return _cache[subject]
    mapping = {"数学": "math_structured.json", "英语": "english_structured.json"}
    fname = mapping.get(subject)
    if not fname:
        path = os.path.join(KB_DIR, f"{subject}_structured.json")
    else:
        path = os.path.join(KB_DIR, fname)
    if not os.path.exists(path):
        _cache[subject] = []
        return []
    with open(path, 'r', encoding='utf-8') as f:
        _cache[subject] = json.load(f)
    return _cache[subject]


def query_standards(subject: str, grade) -> list:
    """
    根据学科和年级返回相关的课标要求。
    grade 可以是数字(如4)或文本(如"四年级")。
    返回匹配该学段的所有条目列表。
    """
    items = _load(subject)
    if not items or grade is None:
        return []

    # 如果传入了文本，提取数字
    if isinstance(grade, str):
        nums = re.findall(r'(\d+)', grade)
        if nums:
            grade = int(nums[0])
        elif not grade.strip():
            return []

    if not isinstance(grade, int):
        return []

    stage_prefix = GRADE_TO_STAGE.get(grade)
    if not stage_prefix:
        return items

    return [item for item in items
            if item.get("学段", "").startswith(stage_prefix)]


def format_standards_for_prompt(standards: list) -> str:
    """将课标条目格式化为提示词可用文本"""
    if not standards:
        return ""

    text = "\n## 课标对照（2022年版）\n"
    text += "以下是该学段学生应达到的内容要求，评分时请对照检验教案的教学内容是否符合年级定位：\n\n"

    by_domain = {}
    for item in standards:
        domain = item.get("领域", "其他")
        if domain not in by_domain:
            by_domain[domain] = []
        by_domain[domain].append(item["要求"])

    for domain, reqs in by_domain.items():
        text += f"### {domain}\n"
        for i, r in enumerate(reqs, 1):
            text += f"{i}. {r}\n"
        text += "\n"

    return text


def search_standards(query_text: str, subject: str, grade=None, top_k: int = 2) -> list:
    """
    检索与批注问题最相关的课标条目（用于"理论依据"标注）。

    返回格式: [{学段, 领域, 要求, 核心素养}]
    """
    items = _load(subject)
    if not items or not query_text:
        return []

    # 优先限定该学段
    candidates = items
    if grade is not None:
        if isinstance(grade, str):
            nums = re.findall(r'(\d+)', grade)
            if nums:
                grade = int(nums[0])
        if isinstance(grade, int):
            stage_prefix = GRADE_TO_STAGE.get(grade)
            if stage_prefix:
                candidates = [i for i in items if i.get("学段", "").startswith(stage_prefix)]

    # 关键词打分：查询文本中的词与课标要求的字面重合度
    def score(item):
        req = item.get("要求", "")
        text = item.get("领域", "") + req
        # 统计查询中的连续 2 字词出现在课标文本中的次数
        s = 0
        for i in range(len(query_text) - 1):
            bigram = query_text[i:i + 2]
            if bigram in text:
                s += 1
        return s

    scored = sorted(candidates, key=score, reverse=True)
    # 去掉零分项
    results = [item for item in scored if score(item) > 0]
    if not results:
        return []
    return results[:top_k]


# ============================================================
# 学生标准：等级换算 + 一级/二级维度体系
# （2026-10-04 新增；数据源自 data/criteria/student_评价指标V3.docx）
# ============================================================

# A/B/C 对应的分值区间（严格按学生标准原文，不同满分各有区间）
GRADE_BANDS = {
    5: {"A": (4, 5), "B": (2, 3), "C": (0, 1)},
    10: {"A": (8, 10), "B": (5, 7), "C": (0, 4)},
    20: {"A": (14, 20), "B": (7, 13), "C": (0, 6)},      # 过程设计（20 分）
}


def score_to_grade(full_mark, score) -> str:
    """
    按学生标准的分值区间，把「维度得分」换算为 A/B/C 等级。

    >>> score_to_grade(10, 8)   # 10 分维度得 8 分
    'A'
    >>> score_to_grade(10, 6)
    'B'
    >>> score_to_grade(5, 1)
    'C'

    未知满分时按比例近似（A≥80%，B≥50%，其余 C）。
    """
    if score is None or full_mark in (None, 0):
        return ""
    try:
        fm = float(full_mark)
        s = float(score)
    except (TypeError, ValueError):
        return ""

    bands = GRADE_BANDS.get(int(fm)) if fm == int(fm) else None
    if bands:
        for g in ("A", "B", "C"):
            lo, hi = bands[g]
            if lo <= s <= hi:
                return g
        return "C" if s < bands["C"][1] else "A"

    ratio = s / fm if fm else 0
    return "A" if ratio >= 0.8 else ("B" if ratio >= 0.5 else "C")


# 一级维度 → 二级维度（学生标准体系）
LEVEL1_TREE = {
    "思想理念": ["教学理念", "课程思政"],
    "学情与目标分析": ["学情分析", "教学目标"],
    "内容与方法": ["教学内容", "教学资源", "教学方法"],
    "过程与实施": ["过程设计", "课堂互动"],
    "评价反馈": ["评价反馈"],
    "文档规范": ["版式观感", "结构完整"],
}

# 二级维度 → 一级维度（反查）
DIM_TO_LEVEL1 = {d: l1 for l1, dims in LEVEL1_TREE.items() for d in dims}

# 一级维度展示顺序
LEVEL1_ORDER = list(LEVEL1_TREE.keys())


def get_level1(dim_name: str) -> str:
    """根据二级维度名返回所属一级维度名（未知则返回空串）"""
    return DIM_TO_LEVEL1.get(str(dim_name).strip(), "")


def group_by_level1(dim_results: list) -> list:
    """
    把维度评分结果按一级维度分组。

    参数: dim_results —— [{"维度名称":…, "满分":…, "得分":…, ...}, ...]
    返回: [{"一级维度":…, "满分":…, "得分":…, "维度列表":[...]}, ...]
    """
    groups = {}
    for d in dim_results or []:
        l1 = get_level1(d.get("维度名称", "")) or "其他"
        g = groups.setdefault(l1, {
            "一级维度": l1,
            "满分": 0,
            "得分": 0,
            "维度列表": [],
        })
        try:
            g["满分"] += float(d.get("满分") or 0)
            g["得分"] += float(d.get("得分") or 0)
        except (TypeError, ValueError):
            pass
        g["维度列表"].append(d)

    ordered = []
    for name in LEVEL1_ORDER:
        if name in groups:
            ordered.append(groups.pop(name))
    ordered.extend(groups.values())      # 兜底：未在标准中的维度
    for g in ordered:
        g["得分"] = round(g["得分"], 1)
        g["满分"] = round(g["满分"], 1)
        # 2026-10-04：按课题组要求，**一级维度不评等级**，只展示其下辖的二级维度；
        #             A/B/C 等级仅用于二级维度（由 score_to_grade 换算）。
    return ordered
