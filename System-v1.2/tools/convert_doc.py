"""
批量把指定目录下的 .doc（旧格式）转为 .docx，输出到 data/plans/（不动原文件）

用法: python tools/convert_doc.py [源目录1] [源目录2] ...
     不带参数时转换默认的两个新教案目录
"""
import os
import sys
import time

import win32com.client as win32
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根目录
if BASE not in sys.path:
    sys.path.insert(0, BASE)

SRC_DIRS = [
    r"E:\项目\数学教案",
    r"E:\项目\英语教案",
]
DST_DIR = os.path.join(BASE, "data/plans")


def convert(src_dir: str, word) -> tuple:
    ok = fail = skip = 0
    docs = sorted(f for f in os.listdir(src_dir) if f.lower().endswith(".doc"))
    if not docs:
        print(f"[{os.path.basename(src_dir)}] 无 .doc 文件")
        return ok, fail, skip
    print(f"[{os.path.basename(src_dir)}] 发现 {len(docs)} 个 .doc")
    for name in docs:
        src = os.path.join(src_dir, name)
        dst = os.path.join(DST_DIR, os.path.splitext(name)[0] + ".docx")
        if os.path.exists(dst):
            print(f"  ○ 已存在，跳过: {name}")
            skip += 1
            continue
        t0 = time.time()
        try:
            doc = word.Documents.Open(src, ReadOnly=True)
            doc.SaveAs2(dst, FileFormat=16)   # 16 = wdFormatXMLDocument
            doc.Close(SaveChanges=0)
            print(f"  ✓ {name}  → {os.path.getsize(dst)/1024:.0f} KB ({time.time()-t0:.1f}s)")
            ok += 1
        except Exception as e:
            print(f"  ✗ 转换失败 {name}: {e}")
            fail += 1
    return ok, fail, skip


def main():
    dirs = sys.argv[1:] or SRC_DIRS
    os.makedirs(DST_DIR, exist_ok=True)
    word = win32.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    total = [0, 0, 0]
    try:
        for d in dirs:
            if not os.path.isdir(d):
                print(f"✗ 目录不存在: {d}")
                continue
            r = convert(d, word)
            total = [a + b for a, b in zip(total, r)]
    finally:
        try:
            word.Quit()
        except Exception:
            pass
    print(f"\n合计：转换 {total[0]}，失败 {total[1]}，跳过 {total[2]}")


if __name__ == "__main__":
    main()
