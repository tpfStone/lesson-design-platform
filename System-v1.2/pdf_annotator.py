"""
PDF 批注生成器
在原始教案 PDF 上添加高亮批注和文字评论

修复记录：
  - v2: 修复重复标注叠加导致文字不可读（矩形去重 + 合并评论到同一高亮）
  - v2: 修复高亮区域超出目标文本（字级矩形精修）
  - v2.1: 修复合并时 annot 对象跨迭代失效的问题（改用 NM 标记追踪）
"""

import os
import re
import fitz
from typing import Dict, Tuple, Optional, List
from collections import defaultdict


# 颜色映射（RGB 浮点值，PyMuPDF 使用 0-1 范围）
# 2026-10-04：等级改为 A/B/C（按学生标准分值区间换算）→ A 绿 / B 橙 / C 红
STATUS_COLORS = {
    "A":      (0.15, 0.52, 0.24),   # 绿色 #27AE60（达标）
    "B":      (0.95, 0.60, 0.07),   # 橙色 #F39C12（需改进）
    "C":      (0.91, 0.30, 0.24),   # 红色 #E74C3C（明显不足）
    # 兼容历史产物中的五档写法
    "优秀":    (0.56, 0.27, 0.68),   # 紫色 #8E44AD
    "亮点":    (0.56, 0.27, 0.68),
    "达标":    (0.15, 0.52, 0.24),   # 绿色 #27AE60
    "基本达标": (0.16, 0.50, 0.73),   # 蓝色 #2980B9
    "部分达标": (0.95, 0.60, 0.07),   # 橙色 #F39C12
    "未达标":  (0.91, 0.30, 0.24),   # 红色 #E74C3C
    "不达标":  (0.91, 0.30, 0.24),
}
DEFAULT_COLOR = (0.50, 0.55, 0.60)

# 高亮不透明度（压低以确保文字始终可读）
HIGHLIGHT_OPACITY = 0.30


# ============================================================
# 矩形精修 — 从整行矩形收缩到字级范围
# ============================================================

def _refine_rect_to_text(page, rect: fitz.Rect, matched_text: str) -> fitz.Rect:
    """
    将 search_for 返回的矩形精确收缩到实际文本区域。

    核心理念：
    - search_for 本身对子串匹配的定位是准确的
    - 问题在于这个矩形是"整行高度"，上下有多余空间
    - 某些 PDF 的 span/word 粒度很粗（一整行一个 span），
      此时不应盲目扩大，而应信任 search_for 的边界

    策略：
    1. 优先信任 search_for 的水平边界（x0, x1）
    2. 垂直方向用 span 数据微调（收缩行高多余空间）
    3. 如果 span 数据不可用，对称收缩垂直方向
    """
    refined = fitz.Rect(rect)

    # === 垂直收缩：search_for 的 y0/y1 包含整行行高 ===
    margin = 4.0
    search_rect = fitz.Rect(
        rect.x0 - 20, rect.y0 - margin + 2,
        rect.x1 + 20, rect.y1 + margin - 2
    )

    blocks = page.get_text("dict", clip=search_rect)["blocks"]
    spans_in_row = []
    for b in blocks:
        if "lines" not in b:
            continue
        for line in b["lines"]:
            line_rect = fitz.Rect(line["bbox"])
            if line_rect.y0 <= rect.y0 and line_rect.y1 >= rect.y1:
                # 同一行
                for span in line["spans"]:
                    spans_in_row.append(fitz.Rect(span["bbox"]))

    if spans_in_row:
        # 找到同行所有 span 的精确高度
        span_min_y = min(sp.y0 for sp in spans_in_row)
        span_max_y = max(sp.y1 for sp in spans_in_row)
        # 取 span 高度，略加 1pt 边距
        refined.y0 = max(rect.y0, span_min_y - 1)
        refined.y1 = min(rect.y1, span_max_y + 1)

    # === 水平方向：除非 search_for 明显偏大，否则信任其边界 ===
    # search_for 返回的宽度一般能精确匹配子串，极少数情况才会偏宽
    # （如 PDF 文本编码导致匹配区域包含了额外的隐藏字符）
    # 这里只做极保守的收缩：如果 rect 宽度超过 300pt
    # （说明可能匹配到了整行），则尝试用 matched_text 估算宽度
    if matched_text and rect.width > 300:
        # 粗略估算：中文字符约 10-12pt 宽，用 11pt 估算
        char_count = len(matched_text.replace(" ", ""))
        est_width = min(char_count * 11, rect.width)
        center_x = (rect.x0 + rect.x1) / 2
        refined.x0 = center_x - est_width / 2
        refined.x1 = center_x + est_width / 2
        # 不超出原始边界
        if refined.x0 < rect.x0:
            refined.x0 = rect.x0
        if refined.x1 > rect.x1:
            refined.x1 = rect.x1

    return refined


# ============================================================
# 矩形重叠检测
# ============================================================

def _rects_overlap(a: fitz.Rect, b: fitz.Rect) -> bool:
    """
    用 IoU（交并比，以较小矩形为分母）判断两个矩形是否实质重叠。
    阈值 0.5：交集超过较小矩形一半面积视为重复。
    """
    inter_x0 = max(a.x0, b.x0)
    inter_y0 = max(a.y0, b.y0)
    inter_x1 = min(a.x1, b.x1)
    inter_y1 = min(a.y1, b.y1)

    if inter_x0 >= inter_x1 or inter_y0 >= inter_y1:
        return False

    inter_area = (inter_x1 - inter_x0) * (inter_y1 - inter_y0)
    area_a = (a.x1 - a.x0) * (a.y1 - a.y0)
    area_b = (b.x1 - b.x0) * (b.y1 - b.y0)
    min_area = min(area_a, area_b)

    if min_area <= 0:
        return False

    return inter_area / min_area > 0.5


def _find_overlapping_nm(page_annotations: List[dict], new_rect: fitz.Rect) -> bool:
    """
    检查页面上是否已有批注的矩形与新矩形重叠。
    返回 True 表示已有覆盖（应避免重复高亮）。
    """
    for rec in page_annotations:
        if _rects_overlap(rec["rect"], new_rect):
            return True
    return False


def _add_overlap_note(page, rect: fitz.Rect, dim_name: str, evaluation: str,
                       analysis: str, suggestion: str):
    """
    当检测到目标区域已有高亮标注时，在旁边添加一个便签图标
    （而非叠加第二个高亮），避免颜色叠加导致文字不可读。

    便签放在目标矩形的右侧或下方，优先右侧。
    """
    comment = _build_comment(dim_name, evaluation, analysis, suggestion)

    # 便签放在目标区域右侧（如果空间够），否则放下方
    note_x0 = rect.x1 + 5
    note_y0 = rect.y0
    note_x1 = note_x0 + 30
    note_y1 = note_y0 + 30

    if note_x1 > page.rect.width - 10:
        # 右侧空间不够，放下方
        note_x0 = rect.x0
        note_y0 = rect.y1 + 3
        note_x1 = note_x0 + 30
        note_y1 = note_y0 + 30

    note_rect = fitz.Rect(note_x0, note_y0, note_x1, note_y1)

    annot = page.add_text_annot(note_rect, f"【{dim_name}】详见批注", icon="Comment")
    annot.set_info(title="AI 评审", content=comment)
    annot.update()


# ============================================================
# 文本搜索（5 级兜底策略）
# ============================================================

def _search_text(page, text: str) -> Tuple[Optional[list], Optional[str]]:
    """
    在页面中搜索文本，5 级兜底策略。

    1. 精确搜索原文
    2. 去掉标点后搜索
    3. 取前 20 个非标点字符搜索
    4. 拆成短句逐句搜索（解决 PDF 断行问题）
    5. 取最长的中文连续字段搜索

    返回: (found_areas, matched_str) 或 (None, None)
    """
    areas = page.search_for(text)
    if areas:
        return areas, text

    clean = re.sub(r'[，。、；：""\u2018\u2019！？《》（）\u3000 \n]', '', text)
    if len(clean) >= 10:
        areas = page.search_for(clean[:30])
        if areas:
            return areas, clean[:30]
        areas = page.search_for(clean[:15])
        if areas:
            return areas, clean[:15]

    half = text[:len(text)//2]
    if len(half) >= 5:
        areas = page.search_for(half)
        if areas:
            return areas, half

    # 策略 3.5: 渐进短前缀
    for n in [20, 15, 10, 8, 6]:
        prefix = text[:n].replace("……", "").replace("…", "").strip()
        if len(prefix) >= 4:
            areas = page.search_for(prefix)
            if areas:
                return areas, prefix

    # 策略 3.6: 尾部及中部片段
    # 有些句子前缀刚好在PDF行边界上断开了，但中后段在同一行内完整
    # 从第4个字开始取不同长度的片段
    for start in [4, 6, 8]:
        for n in [20, 15, 10, 8]:
            if start + n <= len(text):
                segment = text[start:start+n].replace("……", "").replace("…", "").strip()
                if len(segment) >= 6:
                    areas = page.search_for(segment)
                    if areas:
                        return areas, segment

    sentences = re.split(r'[，。；]', text)
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) >= 8:
            areas = page.search_for(sentence)
            if areas:
                return areas, sentence

    words = re.findall(r'[\u4e00-\u9fff]{4,}', text)
    for word in sorted(words, key=len, reverse=True):
        areas = page.search_for(word)
        if areas:
            return areas, word

    return None, None


def _search_by_position(page, position_text: str) -> Tuple[Optional[list], Optional[str]]:
    """根据章节位置描述搜索章节标题"""
    parts = position_text.replace(' ', '').replace('\u3000', '').split('/')
    for part in parts:
        part = part.strip()
        if len(part) >= 3:
            areas = page.search_for(part)
            if areas:
                return areas, part
    return None, None


def _find_page_by_position(doc, position_text: str) -> Optional[int]:
    """根据章节位置描述找到最可能的目标页码"""
    keywords = re.findall(r'[\u4e00-\u9fff]{3,}', position_text)
    keywords.sort(key=len, reverse=True)
    for kw in keywords[:3]:
        for page in doc:
            areas = page.search_for(kw)
            if areas:
                return page.number
    return -1


# ============================================================
# 批注添加
# ============================================================

_annotation_counter = [0]  # 全局计数器，生成唯一 NM


def _build_comment(dim_name: str, evaluation: str, analysis: str, suggestion: str) -> str:
    """构建批注评论文本"""
    comment = f"【{dim_name} — {evaluation}】\n{analysis}"
    if suggestion and suggestion != "无需改进":
        comment += f"\n\n建议：{suggestion}"
    return comment


def _add_highlight(page, rect, dim_name: str, evaluation: str,
                   analysis: str, suggestion: str) -> str:
    """
    在页面上添加高亮批注，返回唯一的 NM 标识字符串。

    不直接返回 annot 对象（跨迭代可能失效），
    而是通过 NM 标识后续定位。
    """
    _annotation_counter[0] += 1
    nm = f"ai_{_annotation_counter[0]:04d}"

    color = STATUS_COLORS.get(evaluation, DEFAULT_COLOR)
    comment = _build_comment(dim_name, evaluation, analysis, suggestion)

    highlight = page.add_highlight_annot(rect)
    highlight.set_colors(stroke=color)
    highlight.set_opacity(HIGHLIGHT_OPACITY)
    highlight.set_info(title="AI 评审", content=comment)
    highlight.update()

    # 设置 NM（通过底层 PDF 字典）
    try:
        highlight.set_name(nm)
    except Exception:
        pass

    return nm


def _add_fallback_annotation(page, dim_name: str, evaluation: str,
                             analysis: str, suggestion: str,
                             position_text: str):
    """兜底：在页面右上角添加便签图标"""
    rect = fitz.Rect(page.rect.width - 40, 10, page.rect.width - 10, 40)

    comment = (f"【{dim_name} — {evaluation}】\n"
               f"位置：{position_text}\n"
               f"{analysis}")
    if suggestion and suggestion != "无需改进":
        comment += f"\n\n建议：{suggestion}"

    annot = page.add_text_annot(rect, comment, icon="Note")
    annot.set_info(title="AI 评审", content=comment)
    annot.update()


# ============================================================
# 附录页 — 收纳无法精确标注的 AI 描述性批注
# ============================================================

def _is_quote_descriptive(quote: str, doc) -> bool:
    """仅当原文在所有页面都搜不到时才判定为描述性。不再使用模式匹配。"""
    if not quote or len(quote) < 8:
        return True
    for page in doc:
        areas, _ = _search_text(page, quote)
        if areas:
            return False
    cn = re.sub(r'[^\u4e00-\u9fff]', '', quote)
    if len(cn) >= 6:
        for page in doc:
            if page.search_for(cn[:8]):
                return False
    return True


def _generate_appendix_page(doc, appendix_items: list):
    """在文档末尾新增一页，简要列出无法精确定位的批注参考。"""
    if not appendix_items:
        return

    page = doc.new_page(width=595.32, height=841.92)
    x0, x1 = 50, 545
    y = 50
    line_h = 16

    def wl(text, size=10, color=(0, 0, 0)):
        nonlocal y
        page.insert_text((x0, y), text, fontname="helv", fontsize=size, color=color)
        y += line_h

    wl("Appendix: Unplaced Annotations", size=14, color=(0.4, 0.4, 0.4))
    y += 8

    for idx, item in enumerate(appendix_items):
        if y > 790:
            page = doc.new_page(width=595.32, height=841.92)
            y = 50
        color = STATUS_COLORS.get(item["evaluation"], DEFAULT_COLOR)
        header = f"#{idx+1} [{item['evaluation']}] {item['dim']}"
        wl(header, size=10, color=color)
        if item["quote"]:
            wl(f"  Quote: {item['quote'][:100]}", size=8, color=(0.3, 0.3, 0.3))
        if item["position"]:
            wl(f"  Pos: {item['position']}", size=8, color=(0.5, 0.5, 0.5))
        page.draw_line((x0, y), (x1, y), color=(0.85, 0.85, 0.85), width=0.5)
        y += 4


# ============================================================
# 主函数
# ============================================================

def generate_annotated_pdf(plan_path: str, result: Dict, output_path: str) -> str:
    """
    在原始教案 PDF 上添加所有批注，输出已标注的 PDF。

    修复：
    - 矩形精修：收缩到字级范围
    - 重叠去重：同一区域多维度引用 → 合并评论文本，不重复画高亮
    - NM 追踪：用唯一名称追踪 annot，避免跨迭代对象失效
    """
    doc = fitz.open(plan_path)
    total_pages = len(doc)

    # 格式防御：仅 PDF 支持高亮批注（PyMuPDF 也能打开 DOCX 等，但 is_pdf=False）
    if not doc.is_pdf:
        print(f"  ⚠ 跳过「已批注 PDF」：{os.path.basename(str(plan_path))} 不是 PDF 格式")
        doc.close()
        return None

    print(f"  原始教案: {total_pages}页")

    stats = {"found": 0, "fallback": 0, "skipped": 0, "note": 0, "appendix": 0}

    # 每页独立的已覆盖矩形列表，用于去重
    page_rects = defaultdict(list)

    # 附录收纳列表
    appendix_items = []

    # 收集所有批注
    all_annotations = []
    for dim in result.get("维度评分", []):
        dim_name = dim.get("维度名称", "")
        for ann in dim.get("批注列表", []):
            all_annotations.append({
                "dim_name": dim_name,
                "quote": ann.get("原文引用", "").strip(),
                "position": ann.get("位置", "").strip(),
                "evaluation": ann.get("评价", ""),
                "analysis": ann.get("具体分析", ""),
                "suggestion": ann.get("建议", "") or ann.get("改进建议", ""),
            })

    # 预扫描：标记哪些引用是 AI 描述性文字（在PDF中不存在）
    for ann_data in all_annotations:
        ann_data["descriptive"] = _is_quote_descriptive(ann_data["quote"], doc)

    desc_count = sum(1 for a in all_annotations if a["descriptive"])
    if desc_count > 0:
        print(f"  检测到 {desc_count} 条引用未在PDF原文中找到（将使用兜底定位）")

    for ann_data in all_annotations:
        quote = ann_data["quote"]
        position = ann_data["position"]
        evaluation = ann_data["evaluation"]
        dim_name = ann_data["dim_name"]
        analysis = ann_data["analysis"]
        suggestion = ann_data["suggestion"]

        if not quote or len(quote) < 4:
            stats["skipped"] += 1
            continue

        # ---- 阶段 1: 文本搜索定位 ----
        matched = False
        for page in doc:
            areas, matched_text = _search_text(page, quote)
            if areas:
                raw_rect = areas[0]
                refined_rect = _refine_rect_to_text(page, raw_rect, matched_text or quote)

                # 去重检查：如果与已有高亮重叠，用便签代替
                if _find_overlapping_nm(page_rects[page.number], refined_rect):
                    _add_overlap_note(page, refined_rect, dim_name, evaluation,
                                      analysis, suggestion)
                    stats["note"] += 1
                else:
                    _add_highlight(page, refined_rect, dim_name, evaluation,
                                   analysis, suggestion)
                    page_rects[page.number].append({
                        "rect": fitz.Rect(refined_rect),
                    })
                    stats["found"] += 1
                matched = True
                break

        if matched:
            continue

        # ---- 阶段 2: 按章节位置定位 ----
        # 文本搜索失败时，用章节标题定位。
        # 在标题下方搜索 quote 的关键词，搜到才标注，搜不到直接兜底便签。
        # 这防止了 "AI描述性原文引用不属于PDF真实文本" 导致的偏移高亮。
        for page in doc:
            areas, _ = _search_by_position(page, position)
            if areas:
                title_rect = areas[0]

                # 在标题下方一行区域内搜索 quote 的关键词
                search_zone = fitz.Rect(
                    title_rect.x0 - 20,
                    title_rect.y1 + 2,
                    title_rect.x1 + 200,
                    title_rect.y1 + 80,  # 标题下方 80pt 范围
                )

                # 尝试多种关键词
                found_in_zone = False
                short_quote = quote[:20].replace("……", "").replace("…", "").strip()
                keywords = [
                    short_quote[:12] if len(short_quote) >= 8 else short_quote,
                    re.sub(r'[（()）]', '', short_quote)[:10] if len(short_quote) >= 6 else short_quote,
                ]
                # 再加一个：取纯中文前10字
                cn_only = re.sub(r'[^\u4e00-\u9fff]', '', quote)[:10]
                if len(cn_only) >= 4:
                    keywords.append(cn_only)

                for kw in keywords:
                    if len(kw) < 3:
                        continue
                    sub_areas = page.search_for(kw, clip=search_zone)
                    if sub_areas:
                        raw_rect = sub_areas[0]
                        refined_rect = _refine_rect_to_text(page, raw_rect, kw)

                        if _find_overlapping_nm(page_rects[page.number], refined_rect):
                            _add_overlap_note(page, refined_rect, dim_name, evaluation,
                                              analysis, suggestion)
                            stats["note"] += 1
                        else:
                            _add_highlight(page, refined_rect, dim_name, evaluation,
                                           analysis, suggestion)
                            page_rects[page.number].append({
                                "rect": fitz.Rect(refined_rect),
                            })
                            stats["found"] += 1
                        found_in_zone = True
                        matched = True
                        break

                if found_in_zone:
                    break
                # 没搜到也不送附录，走阶段3兜底

        if matched:
            continue

        # ---- 阶段 2.5: "全文"类批注 ----
        if "全文" in position:
            # 在首页找教案标题（不再区分描述性，统一处理）
                # 在首页找教案标题
                first_page = doc[0]
                title_found = False
                blocks = first_page.get_text("dict")["blocks"]
                for b in blocks:
                    if "lines" in b:
                        for line in b["lines"]:
                            for span in line["spans"]:
                                text = span["text"].strip()
                                if "教学" in text and len(text) > 6:
                                    areas = first_page.search_for(text)
                                    if areas:
                                        raw_rect = areas[0]
                                        refined_rect = _refine_rect_to_text(first_page, raw_rect, text)
                                        if _find_overlapping_nm(page_rects[0], refined_rect):
                                            _add_overlap_note(first_page, refined_rect, dim_name,
                                                              evaluation, analysis, suggestion)
                                            stats["note"] += 1
                                        else:
                                            _add_highlight(first_page, refined_rect, dim_name,
                                                           evaluation, analysis, suggestion)
                                            page_rects[0].append({"rect": fitz.Rect(refined_rect)})
                                            stats["found"] += 1
                                        title_found = matched = True
                                        break
                                if title_found: break
                        if title_found: break
                    if title_found: break

        if matched:
            continue

        # ---- 阶段 3: 兜底 ----
        # 所有无法精确标注的批注统一走兜底便签

        target_page = _find_page_by_position(doc, position)
        if target_page < 0:
            target_page = 0

        page = doc[target_page]
        _add_fallback_annotation(page, dim_name, evaluation, analysis,
                                 suggestion, position)
        stats["fallback"] += 1

    # === 生成附录页 ===
    if appendix_items:
        _generate_appendix_page(doc, appendix_items)
        print(f"  附录页: 收纳 {len(appendix_items)} 条AI描述性/无法精确定位的批注")

    # 保存
    doc.save(output_path, garbage=4, deflate=True)
    doc.close()

    # 统计报告
    total = stats["found"] + stats["fallback"] + stats["skipped"] + stats["note"] + stats["appendix"]
    print(f"  批注添加: {stats['found']}/{total} 条独立高亮", end="")
    if stats["note"] > 0:
        print(f", {stats['note']} 条便签代替(避免重叠)", end="")
    if stats["appendix"] > 0:
        print(f", {stats['appendix']} 条归入附录", end="")
    if stats["fallback"] > 0:
        print(f", {stats['fallback']} 条兜底便签", end="")
    if stats["skipped"] > 0:
        print(f", {stats['skipped']} 条跳过", end="")
    print()

    return output_path
