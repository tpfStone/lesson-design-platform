"""
批量评分：英语新教案（按内容字数升序），每 3 份一批，支持上限与断点续跑
用法: python _batch_english.py [本次上限份数]
结果: output/_batch_english_summary.json

注：5 份扫描版 PDF（三年级 Unit1/2/3/6 等）需 OCR，耗时远超普通教案，不在本脚本内，建议单独跑。
"""
import sys, os, json, time
import os
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根目录
if BASE not in sys.path:
    sys.path.insert(0, BASE)
from pipeline import load_config
from service import run_annotation, AnnotationError


cfg = load_config(f"{BASE}/config.yaml")

# 按内容字数升序（预检数据）
PLANS = [
    "四年级 上册 Unit 5 Dinner is ready.docx",
    "六年级 下册 PEP英语《Unit2 Last weekend》.docx",
    "Unit+4+go+shopping+Part+A+let's+talk（教学设计）-2025-2026学年人教PEP版英语四年级下册.docx",
    "Unit+1+Class+rules+(Part+B+Let’s+talk-Let’s+learn)（教学设计）-2025-2026学年人教PEP版英语四年级下册.docx",
    "六年级 下册 PEP英语《Unit1 How tall are you》.docx",
    "Unit+4+Helping+in+the+community+第4课时+Part+B+Let's+talk+Look+and+say（教学设计）-2025-2026学年人教PEP版（2024）英语四年级上册+.docx",
    "Unit+6+From+farm+to+table+Part+A（教学设计）-2025-2026学年人教PEP英语四年级下册.docx",
    "六年级 下册 PEP英语《Recycle》.docx",
    "五年级 上册 PEP英语《Unit6 In a nature park》.docx",
    "五年级 下册 PEP英语《Unit4 When is Easter》.docx",
    "五年级 上册 PEP英语《Unit2 My week》.docx",
    "Unit+5+The+weather+and+us+++Part+A+Let’s+talk+&+Look+and+say（教学设计）-2025-2026学年四年级英语上册（人教PEP版）.docx",
    "Unit+2++My+feelings+Part+B+Let's+talk（教学设计）-2026-2027学年人教PEP版英语五年级上册.docx",
    "六年级 下册PEP英语《Unit3 Where did you go》.docx",
    "六年级 下册 PEP英语《Unit4 Then and now》.docx",
]

OUT = f"{BASE}/output/_batch_english_summary.json"

done = {}
if os.path.exists(OUT):
    try:
        for item in json.load(open(OUT, encoding="utf-8")):
            done[item["教案"]] = item
    except Exception:
        pass
print(f"断点续跑：已有 {len(done)} 份结果\n", flush=True)

BATCH = 3
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 0
ran = 0
if LIMIT:
    print(f"本次上限：{LIMIT} 份\n", flush=True)

for bi in range(0, len(PLANS), BATCH):
    if LIMIT and ran >= LIMIT:
        print(f"\n已达本次上限 {LIMIT} 份，停止（重新运行可继续）", flush=True)
        break
    batch = PLANS[bi:bi + BATCH]
    print(f"\n{'#'*70}\n### 第 {bi//BATCH + 1} 批（{len(batch)} 份）\n{'#'*70}", flush=True)
    for plan in batch:
        if LIMIT and ran >= LIMIT:
            break
        if plan in done and done[plan].get("总分"):
            print(f"  ○ 已有结果，跳过: {plan[:40]}", flush=True)
            continue
        print(f"\n>>> {plan}", flush=True)
        ran += 1
        t0 = time.time()
        try:
            out = run_annotation(BASE, cfg, plan, "competition", "default",
                                 suggest=True, dry_run=False,
                                 progress=lambda m: print("   " + m, flush=True))
            r = out["result"]
            dm = sum(d.get("满分", 0) for d in r.get("维度评分", []))
            item = {
                "教案": plan, "学科": out.get("subject"), "年级": out.get("grade"),
                "总分": r.get("评分汇总", {}).get("总分"), "满分": dm,
                "耗时": round(time.time() - t0),
                "维度": [(d["维度名称"], d.get("得分"), d.get("满分")) for d in r.get("维度评分", [])],
                "产物目录": out["out_dir"],
            }
            done[plan] = item
            print(f"  ✅ 总分 {item['总分']}/{dm}（{item['耗时']}秒）", flush=True)
        except AnnotationError as e:
            done[plan] = {"教案": plan, "错误": str(e)}
            print(f"  ❌ 失败: {e}", flush=True)
        except Exception as e:
            done[plan] = {"教案": plan, "错误": f"{type(e).__name__}: {e}"}
            print(f"  ❌ 异常: {type(e).__name__}: {e}", flush=True)
        json.dump(list(done.values()), open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("\n\n=========== 本次结束 ===========", flush=True)
for plan in PLANS:
    it = done.get(plan, {})
    if it.get("总分") is not None:
        print(f"{it['总分']:>5}/{it.get('满分')}  {plan[:56]}", flush=True)
    elif it:
        print(f"ERR    {plan[:56]} {it.get('错误','')[:30]}", flush=True)
    else:
        print(f"待跑    {plan[:56]}", flush=True)
