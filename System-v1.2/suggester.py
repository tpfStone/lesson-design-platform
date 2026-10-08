"""
============================================================
改进建议生成器
基于「设计理论库 + 课标标准库 + 小学教学法库」三库检索 + 推理链提示词
生成具体修改建议（细化建议）
============================================================
"""

import os
import json
import re
from typing import Dict, List

from knowledge_base import load_knowledge_base, search_knowledge_base
from standards import search_standards
from anchors import build_advice_anchor_block


# ============================================================
# 锚点配置读取
# ============================================================

_anchor_mode_cache = None


def _get_anchor_mode() -> str:
    """读取 config.yaml 中的 anchors.mode（enabled=false 时返回 'off'）"""
    global _anchor_mode_cache
    if _anchor_mode_cache is not None:
        return _anchor_mode_cache
    mode = "both"
    try:
        import yaml
        cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            a = cfg.get("anchors", {}) or {}
            if not a.get("enabled", True):
                mode = "off"
            else:
                mode = a.get("mode", "both")
    except Exception:
        pass
    _anchor_mode_cache = mode
    return mode


# ============================================================
# 小学教学法库（数学 / 英语，学段 1-6 年级）
# ============================================================

_methods_cache = {}  # subject -> entries


def _load_methods(subject: str) -> List[Dict]:
    """按学科加载小学教学法库（带缓存）"""
    if subject in _methods_cache:
        return _methods_cache[subject]
    fname = {"数学": "math_methods_primary.json",
             "英语": "english_methods_primary.json"}.get(subject)
    if not fname:
        _methods_cache[subject] = []
        return []
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "knowledge_base", fname)
    if not os.path.exists(path):
        _methods_cache[subject] = []
        return _methods_cache[subject]
    with open(path, "r", encoding="utf-8") as f:
        _methods_cache[subject] = json.load(f)
    return _methods_cache[subject]


def _match_primary_methods(query: str, subject: str, grade, top_k: int = 2) -> List[Dict]:
    """
    匹配小学教学法条目。仅 数学/英语 + 小学学段（1-6 年级）触发。
    打分：query 与条目文本的 2-gram 重合度 + 关键词命中。
    """
    methods = _load_methods(subject)
    if not methods or subject not in ("数学", "英语"):
        return []
    if grade is None:
        return []
    g = grade if isinstance(grade, int) else None
    if g is not None and not (1 <= g <= 6):
        return []  # 初中教案不匹配小学方法库

    def score(m):
        # 拼接条目全部文本字段（兼容数学/英语两种 schema）
        text = " ".join(str(v) for v in m.values() if isinstance(v, str))
        s = 0
        for i in range(len(query) - 1):
            if query[i:i + 2] in text:
                s += 1
        # 关键词强命中
        for kw in ["概念", "意义", "计算", "算理", "算法", "几何", "图形",
                   "测量", "单位", "量感", "统计", "数据", "概率", "随机",
                   "问题解决", "策略", "评价", "反馈", "语音", "拼读", "词汇",
                   "语法", "听力", "口语", "对话", "阅读", "故事", "写作",
                   "课堂", "指令", "提问", "任务"]:
            if kw in query and kw in text:
                s += 2
        return s

    scored = [(score(m), m) for m in methods]
    scored.sort(key=lambda x: x[0], reverse=True)
    picked = [(s, m) for s, m in scored if s > 0][:top_k]
    return [m for _, m in picked]


def _format_method_ref(m: Dict, subject: str) -> str:
    """把教学法条目格式化为参考文本（按学科 schema 适配）"""
    if subject == "数学":
        return (f"[{m.get('领域','')}] {m.get('知识点','')} | "
                f"教学方法：{m.get('教学方法','')}")
    # 英语 schema
    steps = m.get("核心步骤", [])
    if isinstance(steps, str):
        steps = [s for s in steps.replace("；", "。").split("。") if s.strip()]
    steps_txt = "；".join(str(s) for s in steps if str(s).strip())
    return (f"[{m.get('领域','')}] {m.get('方法名','')}"
            f"({m.get('方法名英','')}) | 步骤：{steps_txt}")


# ============================================================
# 建议生成 Prompt（B 方案：推理链）
# ============================================================

SUGGESTION_SYSTEM_PROMPT = """你是一位教学设计优化专家。现在给你一份教案的若干条批注，以及匹配到的设计理论、课标要求和教学法参考，请你为每条批注生成具体的修改建议（细化建议）。

在撰写每条建议前，请遵循三步推理（推理过程不需输出，但建议内容必须体现推理结论）：
1. 定位：判断该批注涉及的教案内容属于什么学段、什么学科领域、什么知识点/教学环节；
2. 对照：结合提供的"设计理论 / 课标要求 / 教学法参考 / 档位参照"，判断该内容本应采用什么样的教学理论与方法；
3. 处方：基于批注的诊断结论，对照"档位参照"中该维度当前档的典型不足与改进目标档的特征，给出针对性的修改做法（含示范写法或具体步骤）。

要求：
1. 修改建议必须具体、可操作，一线教师看了就能照着改（写"怎么改"，给出可执行的步骤或示范写法）
2. 若提供了"档位参照"，建议应指向"改进目标档"的特征（例如当前档典型不足是"只有知识点罗列"，建议就要落到"补充教材位置、知识结构与重难点成因"）
3. 引用理论/课标/教学法时点到即止，重点是"怎么用它来改进"
4. 每条修改建议 80-150 字
5. 建议文本中如需引用，一律使用中文引号（“……”或「……」），**严禁使用英文双引号**——否则会破坏 JSON 结构导致整批建议丢失
6. 只输出一个 JSON 对象，不要任何解释文字、不要 markdown 代码块
7. JSON 格式：{"建议列表": [{"id": 1, "具体建议": "..."}, ...]}"""


def _build_batch_prompt(
    plan_context: str,
    annotations: List[Dict],
) -> str:
    """构建批量建议生成的用户提示词"""
    prompt = "## 教案上下文\n\n"
    prompt += plan_context[:800] + "\n\n"
    prompt += "## 待改进批注列表\n\n"

    for i, ann in enumerate(annotations, 1):
        prompt += f"### 批注 {ann['id']}\n"
        prompt += f"- 维度：{ann.get('dim_name', '')}\n"
        prompt += f"- 位置：{ann.get('位置', '')}\n"
        prompt += f"- 评价：{ann.get('评价', '')}\n"
        prompt += f"- 问题分析：{ann.get('具体分析', '')}\n"
        prompt += f"- 建议(诊断)：{ann.get('建议', '')}\n"
        if ann.get('依据来源'):
            prompt += f"- 依据来源：{ann['依据来源']}\n"
        if ann.get('教学法参考'):
            prompt += f"- 教学法参考：{ann['教学法参考']}\n"
        if ann.get('档位参照'):
            prompt += f"- 档位参照（该维度的分数段特征）：\n{ann['档位参照']}\n"
        prompt += "\n"

    prompt += "## 任务\n\n"
    prompt += f"为以上 {len(annotations)} 条批注生成具体的修改建议（细化建议）。\n"
    prompt += "每条建议须先内化'定位→对照→处方'三步推理，描述'怎么改'，给出可执行步骤或示范写法。\n"
    prompt += "输出 JSON 对象：{\"建议列表\": [{\"id\": 1, \"具体建议\": \"...\"}, ...]}\n"
    prompt += "注意：建议文本内引用一律用中文引号「」或“”，禁止使用英文双引号。\n"
    prompt += "只输出 JSON，不要其他内容。"

    return prompt


def _sanitize_suggestions_json(text: str) -> str:
    """
    启发式修复：把「具体建议」值内部**未转义的英文双引号**替换为中文引号。

    坏样本（真实出现过）：
      {"id": 9, "具体建议": "...完成学习单"我的检验方法"一栏并与同桌交流..."}
                                            ↑ 提前闭合字符串，破坏整个 JSON

    判据：值以 `"}` 结尾，因此值内部的 " 后面接的不是 } （即不是值正常结束）→ 视为裸引号。
    """
    def repl(m):
        val = m.group(2)
        out, open_q = [], True
        for ch in val:
            if ch == '"':
                out.append("“" if open_q else "”")
                open_q = not open_q
            else:
                out.append(ch)
        return m.group(1) + "".join(out) + '"}'

    return re.sub(r'("具体建议"\s*:\s*")([\s\S]*?)"\s*\}', repl, text)


def _extract_json_block(text: str) -> str:
    """从含杂质的输出中提取 JSON 片段（优先对象，其次数组）"""
    m = re.search(r'\{[\s\S]*"建议列表"[\s\S]*\}\s*$', text)
    if m:
        return m.group(0)
    m = re.search(r'\[[\s\S]*\]', text)
    if m:
        return m.group(0)
    m = re.search(r'\{[\s\S]*\}', text)
    return m.group(0) if m else ""


def _parse_suggestions(raw: str) -> List[Dict]:
    """
    解析建议结果（多重容错）：
      1) 直接解析（兼容 {"建议列表": [...]} 与裸数组 [...]）
      2) 提取 JSON 片段后解析
      3) 「具体建议」值内裸英文双引号消毒后重试
    返回 list；全部失败返回 []。
    """
    if not raw:
        return []

    def _try(t):
        if not t:
            return None
        try:
            data = json.loads(t)
        except json.JSONDecodeError:
            return None
        if isinstance(data, dict):
            for key in ("建议列表", "suggestions", "list", "items"):
                if isinstance(data.get(key), list):
                    return data[key]
            return None
        if isinstance(data, list):
            return data
        return None

    text = raw.strip()
    candidates = [text, _extract_json_block(text), _sanitize_suggestions_json(text)]
    for cand in candidates:
        got = _try(cand)
        if got is not None:
            return got
        got = _try(_sanitize_suggestions_json(cand))
        if got is not None:
            return got
    return []


# ============================================================
# 依据来源检索
# ============================================================

def _match_sources(
    query: str,
    subject: str = "",
    grade=None,
) -> Dict:
    """
    同时检索设计理论库、课标库与小学教学法库，标注依据来源类型。

    返回: {"来源类型": ..., "理论条目": ..., "课标原文": ..., "教学法参考": ...}
    """
    sources = {"来源类型": "无", "理论条目": "", "课标原文": "", "教学法参考": ""}

    # 1. 设计理论库
    kb = load_knowledge_base()
    theories = search_knowledge_base(query, kb, top_k=2) if kb else []
    if theories:
        sources["理论条目"] = "、".join(t["title"] for t in theories)

    # 2. 课标库（需要学科）
    standards = search_standards(query, subject, grade, top_k=2) if subject else []
    if standards:
        sources["课标原文"] = "；".join(
            f"[{s.get('学段','')}|{s.get('领域','')}] {s.get('要求','')}"
            for s in standards
        )

    # 3. 小学教学法库（数学/英语 + 小学学段）
    m_methods = _match_primary_methods(query, subject, grade, top_k=1)
    if m_methods:
        sources["教学法参考"] = _format_method_ref(m_methods[0], subject)

    # 判定来源类型
    has_theory = bool(theories)
    has_std = bool(standards)
    if has_theory and has_std:
        sources["来源类型"] = "二者共同"
    elif has_theory:
        sources["来源类型"] = "设计理论"
    elif has_std:
        sources["来源类型"] = "课标标准"

    return sources


# ============================================================
# 批量生成建议
# ============================================================

def generate_suggestions(
    result: Dict,
    plan_text: str,
    provider=None,
    subject: str = "",
    grade=None,
) -> Dict:
    """
    为所有非达标批注匹配依据来源（设计理论+课标+小学教学法），
    并一次性调用 LLM 生成修改建议。

    参数:
      result: LLM 评分结果 JSON
      plan_text: 教案原文
      provider: LLM provider 实例。为 None 时仅做依据匹配。
      subject: 学科（用于检索课标库/教学法库）
      grade: 年级（用于限定学段）

    返回: 更新后的 result
    """
    kb = load_knowledge_base()
    if not kb:
        print("  ⚠ 设计理论库为空，无法生成建议")
        return result

    # 收集所有需要建议的批注
    pending = []
    anchor_mode = _get_anchor_mode()
    use_anchor = anchor_mode in ("advice", "both")

    for dim in result.get("维度评分", []):
        dim_name = dim.get("维度名称", "")
        dim_score = dim.get("得分")
        dim_full = dim.get("满分")
        # 该维度的档位锚点（详细版：当前档 + 改进目标档 + 示例片段）
        dim_anchor = ""
        if use_anchor:
            try:
                dim_anchor = build_advice_anchor_block(subject, dim_name, dim_score, dim_full)
            except Exception:
                dim_anchor = ""

        for ann in dim.get("批注列表", []):
            evaluation = str(ann.get("评价", "")).strip()
            # 2026-10-04：批注等级改为 A/B/C（按学生标准分值区间换算）。
            # 仅对「未达 A」（即 B / C）的批注生成改进建议；
            # 同时兼容历史产物中的五档写法（优秀 / 达标 = 达标态，跳过）。
            if evaluation in ("A", "优秀", "达标"):
                continue

            query = f"{dim_name} {ann.get('位置', '')} {ann.get('具体分析', '')}"
            sources = _match_sources(query, subject, grade)
            if sources["来源类型"] == "无" and not sources["教学法参考"]:
                continue

            # 组装依据来源描述
            parts = [f"来源：{sources['来源类型']}"]
            if sources["理论条目"]:
                parts.append(f"理论：{sources['理论条目']}")
            if sources["课标原文"]:
                parts.append(f"课标：{sources['课标原文']}")
            ann["依据来源"] = " | ".join(parts)
            ann["理论依据"] = sources["理论条目"] or sources["课标原文"]
            if sources["教学法参考"]:
                ann["教学法参考"] = sources["教学法参考"]
            if dim_anchor:
                ann["档位参照"] = dim_anchor

            pending.append({
                "annotation": ann,
                "dim_name": dim_name,
                "index": len(pending) + 1,
            })

    if not pending:
        return result

    if provider:
        items = [{
            "id": p["index"],
            "dim_name": p["dim_name"],
            "位置": p["annotation"].get("位置", ""),
            "评价": p["annotation"].get("评价", ""),
            "具体分析": p["annotation"].get("具体分析", ""),
            "建议": p["annotation"].get("建议", ""),
            "依据来源": p["annotation"].get("依据来源", ""),
            "教学法参考": p["annotation"].get("教学法参考", ""),
            "档位参照": p["annotation"].get("档位参照", ""),
        } for p in pending]

        try:
            prompt = _build_batch_prompt(plan_text, items)
            # max_tokens=8192：批注较多时（非达标 ≥17 条）建议总长可达 2600+ 字，
            # 原先 4096 会被截断 → JSON 解析失败（2026-09-19 实测确证）
            # 2026-09-30：改用 chat_json（结构化输出）+ 容错解析 + 失败重试
            #   原实现用 json.loads 裸解析，模型一旦在建议文本中用未转义的英文双引号就会整批丢失
            raw = ""
            suggestions = []
            for attempt in (1, 2):
                raw = provider.chat_json(SUGGESTION_SYSTEM_PROMPT, prompt,
                                         temperature=0.1, max_tokens=8192)
                # 保留原始输出便于诊断
                try:
                    dbg = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       "output", "debug_suggest_raw.txt")
                    os.makedirs(os.path.dirname(dbg), exist_ok=True)
                    with open(dbg, "w", encoding="utf-8") as f:
                        f.write(raw or "")
                except Exception:
                    pass
                suggestions = _parse_suggestions(raw or "")
                if suggestions:
                    break
                print(f"  ⚠ 建议解析失败（第 {attempt} 次）"
                      f"{'，重试一次…' if attempt == 1 else ''}")

            if suggestions:
                for s in suggestions:
                    sid = s.get("id", 0)
                    if 1 <= sid <= len(pending):
                        pending[sid - 1]["annotation"]["细化建议"] = s.get("具体建议", "")
                print(f"  ✓ 建议生成: {len(suggestions)} 条（1 次 API 调用，含推理链）")
            else:
                print(f"  ⚠ 建议生成失败：两次均无法解析（输出 {len(raw or '')} 字）\n"
                      f"     原始输出已保存至 output/debug_suggest_raw.txt，可据此排查")
        except Exception as e:
            print(f"  ⚠ 建议生成失败: {e}")

    return result
