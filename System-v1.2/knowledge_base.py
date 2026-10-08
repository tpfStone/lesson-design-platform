"""
============================================================
教学设计理论知识库
结构化存储 + 关键词索引，用于匹配批注并生成改进建议
============================================================
"""

import os
import re
from typing import List, Dict, Tuple


# ============================================================
# 知识库构建
# ============================================================

def build_knowledge_base(doc_path: str) -> List[Dict]:
    """
    解析教学设计理论文档，构建结构化知识库。

    返回格式:
    [
      {
        "id": "ADDIE模型",
        "category": "整体教学设计框架",
        "title": "ADDIE 模型(ADDIE Model)",
        "keywords": ["分析", "设计", "开发", "实施", "评估", "教学流程", "系统化"],
        "summary": "ADDIE是一个五阶段教学设计流程...",
        "full_text": "完整原文...",
      },
      ...
    ]
    """
    # 读取文档
    if doc_path.endswith('.docx'):
        from parsers import parse_docx
        text = parse_docx(doc_path)
    else:
        with open(doc_path, 'r', encoding='utf-8') as f:
            text = f.read()

    # 按大类切分
    category_pattern = re.compile(r'\n(?=[一二三四五六七八九十]+、)')
    big_sections = category_pattern.split(text)

    entries = []
    category_map = {
        "一、": "整体教学设计框架",
        "二、": "教学目标设计理论",
        "三、": "教学流程与环节设计理论",
        "四、": "教学方法论模型",
        "五、": "教学评价与认知理论",
    }

    for sec in big_sections:
        sec = sec.strip()
        if not sec:
            continue

        # 提取大类名
        cat_name = ""
        for prefix, name in category_map.items():
            if sec.startswith(prefix):
                cat_name = name
                break
        if not cat_name:
            cat_name = sec.split('\n')[0][:20]

        # 按子节切分（数字编号开头的行）
        sub_pattern = re.compile(r'\n(?=\d+\.\s*[^\d])')
        subs = sub_pattern.split(sec)

        for sub in subs:
            sub = sub.strip()
            if not sub or len(sub) < 50:
                continue

            # 第一行是标题
            lines = sub.split('\n')
            title_line = lines[0].strip()
            # 去掉大类前缀
            title_line = re.sub(r'^[一二三四五六七八九十]+、', '', title_line).strip()

            # 提取标题（去掉编号）
            title_match = re.match(r'\d+\.\s*(.+)$', title_line)
            if title_match:
                title = title_match.group(1).strip()
            else:
                title = title_line[:60]

            # 摘要用前 600 字
            content = '\n'.join(lines[1:])
            summary = content[:600]

            # 自动提取关键词
            keywords = _extract_keywords(title, content)

            entry = {
                "id": _make_id(title),
                "category": cat_name,
                "title": title,
                "keywords": keywords,
                "summary": summary,
                "full_text": sub,
            }
            entries.append(entry)

    return entries


def _make_id(title: str) -> str:
    """生成简短ID"""
    # 去掉括号内容和英文
    clean = re.sub(r'[（(][^）)]*[）)]', '', title)
    clean = re.sub(r'[a-zA-Z\s]', '', clean)
    return clean[:20] if clean else title[:20]


def _extract_keywords(title: str, content: str) -> List[str]:
    """
    自动提取关键词：标题关键词 + 内容高频教育学术语。
    """
    keywords = set()

    # 1. 从标题提取
    title_terms = re.findall(r'[\u4e00-\u9fff]{2,6}', title)
    keywords.update(title_terms)

    # 2. 教育学术语词表（核心标签）
    edu_terms = [
        # 教学流程类
        "导入", "讲授", "探究", "练习", "总结", "讨论", "互动", "合作",
        "自主学习", "小组", "展示", "反思", "评价", "反馈", "巩固",
        # 目标类
        "教学目标", "学习目标", "认知", "技能", "情感", "态度", "价值观",
        "核心素养", "行为目标", "可测量",
        # 方法类
        "问题解决", "案例", "项目", "任务", "情境", "真实情境", "实践",
        "探究式", "发现式", "启发式", "支架", "脚手架", "分层",
        # 动机类
        "动机", "兴趣", "注意力", "参与", "投入", "挑战",
        # 资源类
        "多媒体", "技术", "数字", "信息化", "资源", "课件", "微课",
        # 评价类
        "形成性评价", "总结性评价", "量规", "诊断", "过程性",
        # 设计类
        "教学设计", "系统化", "迭代", "分析", "设计", "开发", "实施",
        # 认知类
        "认知负荷", "记忆", "理解", "应用", "迁移", "建构",
        # 思政类
        "思政", "立德树人", "德育",
        # 学生类
        "学情", "起点", "差异", "个性化", "最近发展区",
    ]
    for term in edu_terms:
        if term in title or term in content[:800]:
            keywords.add(term)

    # 限制数量
    return list(keywords)[:15]


# ============================================================
# 知识库加载（带缓存）
# ============================================================

_kb_cache = None


def load_knowledge_base(doc_path: str = None, force_rebuild: bool = False) -> List[Dict]:
    """加载知识库（首次加载后缓存）"""
    global _kb_cache
    if _kb_cache is not None and not force_rebuild:
        return _kb_cache

    if doc_path is None:
        # 优先使用环境变量（开发机可自定义理论文档路径）
        doc_path = os.environ.get("THEORY_DOC_PATH")

    if doc_path is None:
        # 兜底：按本文件所在位置推算 → 项目目录下的 knowledge_base/教学设计理论.docx
        # 用相对项目根的方式，保证整个文件夹拷到任何电脑、任何盘符都能找到该文档
        _here = os.path.dirname(os.path.abspath(__file__))
        doc_path = os.path.join(_here, "knowledge_base", "教学设计理论.docx")

    if not os.path.exists(doc_path):
        print(f"  ⚠ 理论知识文档不存在: {doc_path}")
        return []

    _kb_cache = build_knowledge_base(doc_path)
    print(f"  ✓ 知识库加载完成: {len(_kb_cache)} 个理论条目")
    return _kb_cache


# ============================================================
# 关键词检索
# ============================================================

def search_knowledge_base(
    query_text: str,
    kb: List[Dict] = None,
    top_k: int = 3,
) -> List[Dict]:
    """
    根据查询文本检索最相关的理论知识条目。

    参数:
      query_text: 查询文本（如批注的「具体分析」「位置」等）
      kb: 知识库，为None时自动加载
      top_k: 返回最相关的条目数

    返回: 按相关度排序的知识条目列表
    """
    if kb is None:
        kb = load_knowledge_base()
    if not kb:
        return []

    # 提取查询关键词
    query_kw = _extract_keywords("", query_text)

    # 计算每项的相关度得分
    scored = []
    for entry in kb:
        score = 0
        entry_kw = set(entry["keywords"])

        # 关键词匹配
        for qk in query_kw:
            if qk in entry_kw:
                score += 3
            # 模糊匹配
            for ek in entry_kw:
                if qk in ek or ek in qk:
                    score += 1

        # 标题匹配加分
        for qk in query_kw:
            if qk in entry["title"]:
                score += 5

        # 类别相关性
        category_boost = {
            "教学流程与环节设计理论": {"互动", "讨论", "合作", "导入", "讲授", "探究"},
            "教学目标设计理论": {"目标", "认知", "技能", "情感", "素养"},
            "教学方法论模型": {"方法", "策略", "问题", "项目", "案例", "探究"},
            "教学评价与认知理论": {"评价", "反馈", "量规", "诊断", "认知"},
            "整体教学设计框架": {"设计", "系统", "流程", "分析"},
        }
        for cat, terms in category_boost.items():
            if entry["category"] == cat:
                for qk in query_kw:
                    if qk in terms:
                        score += 2

        if score > 0:
            scored.append((score, entry))

    # 排序取 top_k
    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored[:top_k]]
