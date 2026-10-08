"""
批量评分：英语 5 份扫描版 PDF（需 OCR，逐份串行）
用法: python _batch_en_pdf.py
结果: output/_batch_en_pdf_summary.json（每份完成即落盘，支持断点续跑）
日志: output/_batch_en_pdf_log.txt（脚本自带，不依赖 shell 重定向）
"""
import sys, os, json, time
import os
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根目录
if BASE not in sys.path:
    sys.path.insert(0, BASE)
from pipeline import load_config
from service import run_annotation, AnnotationError


LOG_PATH = f"{BASE}/output/_batch_en_pdf_log.txt"


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


cfg = load_config(f"{BASE}/config.yaml")

PLANS = [
    "三年级上Unit 1 Making friends.pdf",
    "三年级下 Unit 1 Meeting new people.pdf",
    "三年级下 Unit 2 My words and actions.pdf",
    "三年级下 Unit 3 Tools and senses for learning.pdf",
    "三年级下 Unit 6 Numbers in life.pdf",
]
OUT = f"{BASE}/output/_batch_en_pdf_summary.json"

# 载入已有结果（只保留成功的）
done = {}
if os.path.exists(OUT):
    try:
        for item in json.load(open(OUT, encoding="utf-8")):
            if item.get("总分") is not None:
                done[item["教案"]] = item
    except Exception:
        pass
log(f"启动：已有 {len(done)} 份成功结果（断点续跑）")

for i, plan in enumerate(PLANS, 1):
    if plan in done:
        log(f"○ [{i}/5] 已有结果，跳过: {plan}")
        continue
    log(f"=== [{i}/5] 开始: {plan}（扫描版，先 OCR）===")
    t0 = time.time()
    try:
        out = run_annotation(BASE, cfg, plan, "competition", "default",
                             suggest=True, dry_run=False,
                             progress=lambda m: log("   " + m))
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
        log(f"✅ 完成 [{i}/5] 总分 {item['总分']}/{dm}（{item['耗时']}秒）")
    except AnnotationError as e:
        log(f"❌ 失败 [{i}/5]: {e}")
    except Exception as e:
        log(f"❌ 异常 [{i}/5]: {type(e).__name__}: {e}")
    json.dump(list(done.values()), open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

log("========== 全部结束 ==========")
for plan in PLANS:
    it = done.get(plan, {})
    if it.get("总分") is not None:
        log(f"  {it['总分']:>5}/{it.get('满分')}  耗时{it.get('耗时',0)}秒  {plan[:52]}")
    else:
        log(f"  未完成    {plan[:52]}")
