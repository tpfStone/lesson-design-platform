"""
============================================================
Word（DOCX）批注生成器
在原始教案 Word 文档上添加「Word 原生批注」（右侧批注气泡）

定位策略（三级 + 兜底）：
  1. 精确：段落内含引文 → 在段落内按 run 边界定位，锚定覆盖引文的 run 序列
  2. 段落级：引文跨 run 无法切分 → 锚定整个段落
  3. 位置兜底：引文找不到 → 用「位置」字段（如"一、（二）"）定位到对应段落
  4. 文末汇总：以上均失败 → 汇总到文末「未定位批注」清单（信息不丢失）

依赖：python-docx >= 1.2.0（原生 add_comment 支持）
============================================================
"""

import os
import re
from typing import Dict, List, Optional, Tuple, Any

from docx import Document
from docx.text.paragraph import Paragraph


DEFAULT_AUTHOR = "AI批注助手"
DEFAULT_INITIALS = "AI"

# 单条批注内各字段的字数上限（防止气泡过长）
FIELD_LIMIT = 260


def _clip(text: str, limit: int = FIELD_LIMIT) -> str:
    t = (text or "").strip().replace("\n", " ")
    if len(t) <= limit:
        return t
    return t[:limit].rstrip() + "…"


# ============================================================
# 遍历：正文 + 表格内段落（Word 教案常用表格排布）
# ============================================================

def _iter_all_paragraphs(doc) -> List[Paragraph]:
    """收集文档正文与表格中的全部段落（去重，保持顺序）"""
    paras: List[Paragraph] = []
    seen = set()

    def add(p: Paragraph):
        key = id(p._p)
        if key not in seen:
            seen.add(key)
            paras.append(p)

    for p in doc.paragraphs:
        add(p)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    add(p)
                # 嵌套表格（如教学设计表格里再嵌表格）
                for nested in cell.tables:
                    for r2 in nested.rows:
                        for c2 in r2.cells:
                            for p in c2.paragraphs:
                                add(p)
    return paras


# ============================================================
# 定位
# ============================================================

def _find_run_span(paragraph: Paragraph, quote: str) -> Optional[Tuple[int, int]]:
    """
    在段落内查找覆盖 quote 的 run 索引范围（整 run 边界）。
    返回 (start_idx, end_idx)（闭区间）或 None。
    """
    runs = paragraph.runs
    if not runs:
        return None
    spans = []
    pos = 0
    for i, r in enumerate(runs):
        t = r.text or ""
        spans.append((i, pos, pos + len(t)))
        pos += len(t)
    full = "".join(r.text or "" for r in runs)
    if not full:
        return None
    idx = full.find(quote)
    if idx < 0:
        return None
    end = idx + len(quote)
    start_run = end_run = None
    for i, s, e in spans:
        if start_run is None and e > idx:
            start_run = i
        if s < end:
            end_run = i
    if start_run is None or end_run is None or end_run < start_run:
        return None
    return (start_run, end_run)


def _match_variants(quote: str) -> List[str]:
    """
    生成降级匹配候选（移植自 pdf_annotator._search_text 的 6 级策略）：
      ① 精确原文
      ② 去标点后（前 30 / 15 字）
      ③ 前半段
      ④ 渐进短前缀（20/15/10/8/6 字）
      ⑤ 中后段片段（从第 4/6/8 字起，取 20/15/10/8 字）
      ⑥ 最长中文连续字段
    AI 的「原文引用」常为概括性文字/与原文存在标点差异，逐字匹配命中率低，故逐级降级。
    """
    cands: List[str] = []
    q = (quote or "").strip()
    if not q:
        return cands

    # ① 精确
    cands.append(q)

    # ② 去标点
    clean = re.sub(r'[，。、；：""\u2018\u2019！？《》（）\[\]【】\u3000 \n\t]', "", q)
    if len(clean) >= 10:
        cands.append(clean[:30])
        cands.append(clean[:15])

    # ③ 前半段
    half = q[:len(q) // 2]
    if len(half) >= 5:
        cands.append(half)

    # ④ 渐进短前缀
    for n in (20, 15, 10, 8, 6):
        prefix = q[:n].replace("……", "").replace("…", "").strip()
        if len(prefix) >= 4:
            cands.append(prefix)

    # ⑤ 中后段片段（解决前缀落在段落边界/被截断的情况）
    for start in (4, 6, 8):
        for n in (20, 15, 10, 8):
            if start + n <= len(q):
                seg = q[start:start + n].replace("……", "").replace("…", "").strip()
                if len(seg) >= 6:
                    cands.append(seg)

    # ⑥ 最长中文连续字段
    cn_segs = re.findall(r"[\u4e00-\u9fff]{6,}", q)
    if cn_segs:
        cands.append(max(cn_segs, key=len)[:25])

    # 去重保序
    seen, out = set(), []
    for c in cands:
        c = (c or "").strip()
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _locate_quote(paragraphs: List[Paragraph], texts: List[str],
                  quote: str) -> Optional[Tuple[Paragraph, Tuple[int, int], str]]:
    """
    按 6 级降级策略在段落中定位引文。
    返回 (段落, (start_run, end_run), 命中的候选文本) 或 None
    """
    for cand in _match_variants(quote):
        if len(cand) < 4:
            continue
        for p, t in zip(paragraphs, texts):
            if not t or cand not in t:
                continue
            span = _find_run_span(p, cand)
            if span:
                return p, span, cand
    return None


def _locate_by_position(paragraphs: List[Paragraph], position: str) -> Optional[Paragraph]:
    """用「位置」字段（如 '一、（二）' / '2.' / '（三）'）定位到含该编号的段落"""
    if not position:
        return None
    cands = re.findall(r"[（(][^）)]{1,12}[）)]|[一二三四五六七八九十]+、|\d+[\.、]", position)
    cands = [c for c in cands if c]
    if not cands:
        # 没有编号结构，退化为用前 6 个字匹配
        head = position.strip()[:6]
        cands = [head] if head else []
    for p in paragraphs:
        t = (p.text or "").strip()
        if not t:
            continue
        for c in cands:
            if c in t:
                return p
    return None


# ============================================================
# 批注文本
# ============================================================

def _build_comment_text(a: Dict) -> str:
    """完整版批注内容：评价 + 分析 + 诊断 + 细化建议 + 依据来源 + 教学法参考"""
    lines = [f"[{a.get('dim_name','')} · {a.get('evaluation','')}]"]
    if a.get("analysis"):
        lines.append(f"分析：{_clip(a['analysis'])}")
    if a.get("suggestion"):
        lines.append(f"诊断：{_clip(a['suggestion'])}")
    if a.get("detail"):
        lines.append(f"细化建议：{_clip(a['detail'])}")
    if a.get("basis"):
        lines.append(f"依据来源：{_clip(a['basis'], 200)}")
    if a.get("method_ref"):
        lines.append(f"教学法参考：{_clip(a['method_ref'], 160)}")
    return "\n".join(lines)


def _safe_add_comment(doc, runs, text: str, author: str, initials: str) -> bool:
    """安全添加批注（过滤空 run、异常捕获）"""
    runs = [r for r in (runs or []) if (r.text or "").strip()]
    if not runs:
        return False
    try:
        doc.add_comment(runs, text=text, author=author, initials=initials)
        return True
    except Exception as e:
        print(f"    ⚠ 添加批注失败：{e}")
        return False


# ============================================================
# 主流程
# ============================================================

def generate_annotated_docx(
    plan_path: str,
    result: Dict,
    output_path: str,
    author: str = DEFAULT_AUTHOR,
    initials: str = DEFAULT_INITIALS,
) -> Optional[str]:
    """
    在教案 Word 上添加原生批注，另存为 output_path。

    返回: 输出文件路径（成功）或 None（失败/非 docx）
    """
    if not str(plan_path).lower().endswith(".docx"):
        print(f"  ⚠ 跳过「已批注 Word」：{os.path.basename(str(plan_path))} 不是 DOCX 格式")
        return None

    try:
        doc = Document(plan_path)
    except Exception as e:
        print(f"  ⚠ 无法打开 Word 文档：{e}")
        return None

    # 收集批注
    annotations = []
    for dim in result.get("维度评分", []):
        dim_name = dim.get("维度名称", "")
        for ann in dim.get("批注列表", []):
            annotations.append({
                "dim_name": dim_name,
                "quote": (ann.get("原文引用") or "").strip(),
                "position": (ann.get("位置") or "").strip(),
                "evaluation": ann.get("评价", ""),
                "analysis": ann.get("具体分析", ""),
                "suggestion": ann.get("建议", ""),
                "detail": ann.get("细化建议", ""),
                "basis": ann.get("依据来源", ""),
                "method_ref": ann.get("教学法参考", ""),
            })

    if not annotations:
        print("  ⚠ 没有可批注的内容")
        return None

    paragraphs = _iter_all_paragraphs(doc)
    print(f"  原始教案: {len(paragraphs)} 个段落（含表格）")

    stats = {"精确": 0, "降级": 0, "位置": 0, "未定位": 0}
    unresolved = []

    # 段落文本缓存（避免重复拼接 run 文本）
    texts = [(p.text or "") for p in paragraphs]

    for a in annotations:
        quote = a["quote"]
        text = _build_comment_text(a)

        # ---- 策略 1/2：引文定位（6 级降级匹配 → 精确 run 边界）----
        hit = _locate_quote(paragraphs, texts, quote) if len(quote) >= 4 else None
        if hit:
            p, (i, j), matched = hit
            if _safe_add_comment(doc, p.runs[i:j + 1], text, author, initials):
                if matched == quote:
                    stats["精确"] += 1
                else:
                    stats["降级"] += 1
            else:
                unresolved.append(a)
                stats["未定位"] += 1
        else:
            # ---- 策略 3：位置字段兜底 ----
            p = _locate_by_position(paragraphs, a["position"])
            if p is not None and _safe_add_comment(doc, p.runs, text, author, initials):
                stats["位置"] += 1
            else:
                unresolved.append(a)
                stats["未定位"] += 1

    # ---- 策略 4：文末汇总未定位批注 ----
    if unresolved:
        doc.add_paragraph("")
        head = doc.add_paragraph()
        head.add_run("未定位批注汇总").bold = True
        tip = doc.add_paragraph()
        tip.add_run(
            f"以下 {len(unresolved)} 条批注的原文引用未能在教案中找到对应文字，"
            "故汇总于此（内容完整保留）："
        ).italic = True
        for a in unresolved:
            p = doc.add_paragraph()
            run = p.add_run(f"◆ [{a['dim_name']} · {a['evaluation']}] 位置：{a['position'] or '未标注'}")
            run.bold = True
            q = doc.add_paragraph()
            q.add_run(f"原文引用：{a['quote'] or '（无）'}")
            # 批注锚定在本条标题段（跨段落 run 组合不被支持）
            _safe_add_comment(doc, p.runs, _build_comment_text(a), author, initials)

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    try:
        doc.save(output_path)
    except Exception as e:
        print(f"  ⚠ 保存已批注 Word 失败：{e}")
        return None

    total = sum(stats.values())
    print(f"  ✓ 已批注 Word: {total} 条批注（精确 {stats['精确']}、降级匹配 {stats['降级']}、"
          f"位置兜底 {stats['位置']}、文末汇总 {stats['未定位']}）")
    return output_path
