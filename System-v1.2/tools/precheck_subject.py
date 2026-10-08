"""预检：对两个新教案目录的全部文件跑学科识别（只读），结果写 UTF-8 文件"""
import sys, os
import os
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根目录
if BASE not in sys.path:
    sys.path.insert(0, BASE)
from parsers import detect_subject

SRC_DIRS = [("数学", r"E:\项目\数学教案"), ("英语", r"E:\项目\英语教案")]
PLANS = r"E:\BiaoZhu\data\plans"
OUT = r"E:\BiaoZhu\_precheck_out.txt"

lines = []
rows = []
for expect, d in SRC_DIRS:
    for f in sorted(os.listdir(d)):
        base, ext = os.path.splitext(f)
        if ext.lower() not in (".doc", ".docx", ".pdf"):
            continue
        cand = [os.path.join(PLANS, base + ".docx"), os.path.join(PLANS, base + ".pdf")]
        path = next((c for c in cand if os.path.exists(c)), None)
        if not path:
            rows.append((expect, f, "文件未就位", 0))
            continue
        try:
            if path.lower().endswith(".docx"):
                from parsers import parse_document
                text = parse_document(path)
            else:
                import fitz
                doc = fitz.open(path)
                text = "".join(p.get_text() for p in doc)
                doc.close()
        except Exception as e:
            rows.append((expect, f, f"解析失败:{str(e)[:24]}", 0))
            continue
        text = text.strip()
        if len(text) < 100:
            rows.append((expect, f, "疑似扫描版(需OCR)", len(text)))
            continue
        subj = detect_subject(os.path.basename(path), text) or "（未识别）"
        rows.append((expect, f, subj, len(text)))

lines.append(f"{'预期':<6}{'识别':<12}{'字数':>7}  文件")
lines.append("-" * 80)
bad = []
for expect, name, subj, n in rows:
    ok = (subj == expect)
    lines.append(f"{expect:<6}{subj:<12}{n:>7}  {name}{'' if ok else '   ❌ 异常'}")
    if not ok:
        bad.append((expect, name, subj, n))

lines.append("")
lines.append(f"共 {len(rows)} 份 | 识别正常 {len(rows)-len(bad)} | 异常 {len(bad)}")
if bad:
    lines.append("\n=== 异常清单（需处理）===")
    for expect, name, subj, n in bad:
        lines.append(f"  [{expect}] {name}  →  识别为「{subj}」（{n} 字）")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("已写入", OUT, "| 异常数:", len(bad))
