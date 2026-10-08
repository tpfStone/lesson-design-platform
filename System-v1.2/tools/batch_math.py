"""
批量评分：数学新教案（按内容字数升序 = 优先可能低分的），每 3 份一批
结果写 output/_batch_math_summary.json
"""
import sys, os, json, time
import os
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根目录
if BASE not in sys.path:
    sys.path.insert(0, BASE)
from pipeline import load_config
from service import run_annotation, AnnotationError


cfg = load_config(f"{BASE}/config.yaml")

# 按字数升序（预检数据），已跑过的两份排除
PLANS = [
    "小学数学人教版（新教材）第四单元第6课时 平移和旋转的应用 教案.docx",
    "小学数学人教版（新教材）六年级上册第四单元圆第2课时 扇形的认识 教案.docx",
    "小学数学人教版（新教材）第四单元第5课时 旋转(2) 教案.docx",
    "小学数学人教版（新教材）有趣的密铺 教案.docx",
    "小学数学人教版（新教材）五年级上册第五单元第1课时 用字母表示数 教案.docx",
    "5.3++稍复杂的分数除法问题（教案）2026-2027学年青岛版六年级数学上册.docx",
    "第五单元+有趣的平面图形（二）（教案）-2025-2026学年北师大版数学二年级下册.docx",
    "数学《第八单元_分数的初步认识》教案教学设计.docx",
    "26秋人教版三年级数学上册数字编码第1课时认识数字编码教学设计.docx",
    "数学《第七单元_图形的运动(二)》教案教学设计.docx",
    "《第二单元_万以内的加法和减法(一)》教案教学设计.docx",
    "数学《第八单元_平均数与条形统计图》教案教学设计.docx",
    "26秋人教版三年级数学上册第一单元观察物体第2课时认识长方体和正方体的展开图教学设计.docx",
    "教材数学《第三单元_角的度量》教案教学设计.docx",
    "26秋人教版三年级数学上册第五单元线和角第4课时认识锐角和钝角教学设计.docx",
    "数学《第九单元_数学广角_鸡兔同笼》教案教学设计.docx",
    "26秋人教版三年级数学上册第五单元线和角第3课时角的初步认识教学设计.docx",
    "小学数学 人教版（新教材） 四年级下册 7 图形的运动（二）轴对称教案.docx",
]
# 修正文件名（前两份的"教材"前缀/实际名以 data/plans 为准，跑之前校验）
PLANS = [
    "小学数学人教版（新教材）第四单元第6课时 平移和旋转的应用 教案.docx",
    "小学数学人教版（新教材）六年级上册第四单元圆第2课时 扇形的认识 教案.docx",
    "小学数学人教版（新教材）第四单元第5课时 旋转(2) 教案.docx",
    "小学数学人教版（新教材）有趣的密铺 教案.docx",
    "小学数学人教版（新教材）五年级上册第五单元第1课时 用字母表示数 教案.docx",
    "5.3++稍复杂的分数除法问题（教案）2026-2027学年青岛版六年级数学上册.docx",
    "第五单元+有趣的平面图形（二）（教案）-2025-2026学年北师大版数学二年级下册.docx",
    "数学《第八单元_分数的初步认识》教案教学设计.docx",
    "26秋人教版三年级数学上册数字编码第1课时认识数字编码教学设计.docx",
    "数学《第七单元_图形的运动(二)》教案教学设计.docx",
    "《第二单元_万以内的加法和减法(一)》教案教学设计.docx",
    "数学《第八单元_平均数与条形统计图》教案教学设计.docx",
    "26秋人教版三年级数学上册第一单元观察物体第2课时认识长方体和正方体的展开图教学设计.docx",
    "数学《第三单元_角的度量》教案教学设计.docx",
    "26秋人教版三年级数学上册第五单元线和角第4课时认识锐角和钝角教学设计.docx",
    "数学《第九单元_数学广角_鸡兔同笼》教案教学设计.docx",
    "26秋人教版三年级数学上册第五单元线和角第3课时角的初步认识教学设计.docx",
    "小学数学 人教版（新教材） 四年级下册 7 图形的运动（二）轴对称教案.docx",
]

OUT = f"{BASE}/output/_batch_math_summary.json"

# 断点续跑：已有结果则跳过
done = {}
if os.path.exists(OUT):
    try:
        for item in json.load(open(OUT, encoding="utf-8")):
            done[item["教案"]] = item
    except Exception:
        pass
print(f"断点续跑：已有 {len(done)} 份结果\n", flush=True)

BATCH = 3
# 本次最多跑 N 份（0=不限），用法: python _batch_math.py 6
LIMIT = 0
if len(sys.argv) > 1:
    try:
        LIMIT = int(sys.argv[1])
    except ValueError:
        pass
ran = 0
if LIMIT:
    print(f"本次上限：{LIMIT} 份（跑完即停，可再次运行继续）\n", flush=True)

for bi in range(0, len(PLANS), BATCH):
    if LIMIT and ran >= LIMIT:
        print(f"\n已达到本次上限 {LIMIT} 份，停止（重新运行本脚本可继续剩余份数）", flush=True)
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
        # 每份完成即落盘
        json.dump(list(done.values()), open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # 批次小结
    print(f"\n--- 第 {bi//BATCH + 1} 批小结 ---", flush=True)
    for plan in batch:
        it = done.get(plan, {})
        if it.get("总分") is not None:
            print(f"  {it['总分']:>3}/{it.get('满分')} 分  {plan[:46]}", flush=True)
        else:
            print(f"  ERR     {plan[:46]}  {it.get('错误','')[:40]}", flush=True)

print("\n\n=========== 全部完成 ===========", flush=True)
for plan in PLANS:
    it = done.get(plan, {})
    if it.get("总分") is not None:
        print(f"{it['总分']:>3}/{it.get('满分')}  {plan[:52]}", flush=True)
    else:
        print(f"ERR   {plan[:52]} {it.get('错误','')[:30]}", flush=True)
