"""
锚点 A/B 验证 v2：增量保存 + 续跑（修 v1 两个问题）
- 每次评分后立即落盘 output/anchors/ab_raw/{教案}_{on|off}.json
- 捕获 SystemExit（do_annotate 内部 sys.exit）
- 日志写文件，避免管道吞输出
"""
import sys, os, json, copy, statistics, traceback, time
import os
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根目录
if BASE not in sys.path:
    sys.path.insert(0, BASE)
from pipeline import do_annotate, load_config


RAW = f"{BASE}/output/anchors/ab_raw"
LOG = f"{BASE}/output/anchors/ab_log.txt"
os.makedirs(RAW, exist_ok=True)

SAMPLES = [
    ("《多位数乘一位数》.pdf", "数学", "低分"),
    ("《异分母分数加、减法》教学设计 张凤敏 .pdf", "数学", "中分"),
    ("侯淑颖-六年级数学-圆的面积.pdf", "数学", "高分"),
    ("《Unit5 A Let's learn》教学设计.pdf", "英语", "低分"),
    ("《I was born in January》.pdf", "英语", "高分"),
]

cfg0 = load_config(f"{BASE}/config.yaml")


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def raw_path(plan, on):
    safe = "".join(c for c in plan if c not in '\\/:*?"<>|').replace(" ", "_")[:40]
    return os.path.join(RAW, f"{safe}_{'on' if on else 'off'}.json")


def run_one(plan, on):
    """跑一次评分并落盘（已存在则跳过）"""
    p = raw_path(plan, on)
    if os.path.exists(p):
        log(f"跳过（已有）: {plan} {'开' if on else '关'}")
        return json.load(open(p, encoding="utf-8"))
    cfg = copy.deepcopy(cfg0)
    cfg.setdefault("output", {})["dir"] = "./output_ab"
    cfg["anchors"] = {"enabled": on, "mode": "both"}
    try:
        r = do_annotate(BASE, cfg, plan, "competition", "default", dry_run=False, suggest=False)
        if r is None:
            log(f"❌ 返回空: {plan} {'开' if on else '关'}")
            return None
        json.dump(r, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        log(f"✓ 完成: {plan} {'开' if on else '关'} 总分={r.get('评分汇总', {}).get('总分')}")
        return r
    except SystemExit as e:
        log(f"❌ SystemExit({e}): {plan} {'开' if on else '关'}")
        return None
    except Exception as e:
        log(f"❌ 异常: {plan} {'开' if on else '关'} {e}")
        log(traceback.format_exc()[:500])
        return None


def dim_scores(r):
    return {d["维度名称"]: (d.get("得分"), d.get("满分")) for d in r.get("维度评分", [])}


report = {"样本": [], "汇总": {}}
off_sds, on_sds = [], []

for plan, subject, level in SAMPLES:
    log(f"--- [{level}] {plan} ---")
    r_off = run_one(plan, False)
    r_on = run_one(plan, True)
    if not r_off or not r_on:
        log(f"跳过统计（数据不全）: {plan}")
        continue

    off, on = dim_scores(r_off), dim_scores(r_on)
    dims = list(off.keys())
    rows, n_off, n_on = [], [], []
    for d in dims:
        so, fo = off[d]
        sn, fn = on[d]
        n_off.append(so / fo if fo else 0)
        n_on.append(sn / fn if fn else 0)
        rows.append({"维度": d, "满分": fo, "关锚点": so, "开锚点": sn, "差值": (sn or 0) - (so or 0)})

    sd_off = statistics.pstdev(n_off)
    sd_on = statistics.pstdev(n_on)
    off_sds.append(sd_off)
    on_sds.append(sd_on)

    def bands(ns):
        b = [0, 0, 0, 0]
        for n in ns:
            b[0 if n < .25 else 1 if n < .5 else 2 if n < .75 else 3] += 1
        return b

    t_off = r_off.get("评分汇总", {}).get("总分")
    t_on = r_on.get("评分汇总", {}).get("总分")
    log(f"  总分 {t_off} → {t_on} | 标准差 {sd_off:.3f} → {sd_on:.3f} | 档位 {bands(n_off)} → {bands(n_on)}")

    report["样本"].append({
        "教案": plan, "学科": subject, "水平": level,
        "总分_关": t_off, "总分_开": t_on,
        "标准差_关": round(sd_off, 3), "标准差_开": round(sd_on, 3),
        "档位_关": bands(n_off), "档位_开": bands(n_on), "维度明细": rows,
    })

if off_sds and on_sds:
    report["汇总"] = {
        "样本数": len(off_sds),
        "平均标准差_关": round(statistics.mean(off_sds), 3),
        "平均标准差_开": round(statistics.mean(on_sds), 3),
        "区分度变化": round(statistics.mean(on_sds) - statistics.mean(off_sds), 3),
        "总分开_均值": round(statistics.mean([s["总分_开"] for s in report["样本"] if isinstance(s["总分_开"], (int, float))]), 1),
        "总分关_均值": round(statistics.mean([s["总分_关"] for s in report["样本"] if isinstance(s["总分_关"], (int, float))]), 1),
    }

with open(f"{BASE}/output/anchors/ab_result.json", "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=1)

md = ["# 锚点注入 A/B 验证报告\n",
      f"- 样本：{len(report['样本'])} 份（数学/英语）",
      "- 对照：关闭锚点 vs 开启锚点（同模型、温度 0.1，仅评分阶段，未生成建议）",
      "- 说明：A/B 原始评分结果保存在 output/anchors/ab_raw/，可复核\n",
      "## 汇总\n"]
if report.get("汇总"):
    s = report["汇总"]
    md += ["| 指标 | 关闭锚点 | 开启锚点 | 变化 |", "|------|:---:|:---:|:---:|",
           f"| 维度得分平均标准差（归一化） | {s['平均标准差_关']} | {s['平均标准差_开']} | {s['区分度变化']:+} |",
           f"| 总分均值 | {s['总分关_均值']} | {s['总分开_均值']} | {round(s['总分开_均值']-s['总分关_均值'],1):+} |", ""]
md.append("## 各教案明细\n")
for s in report["样本"]:
    md += [f"### [{s['水平']}] {s['教案']}（{s['学科']}）\n",
           f"- 总分：关闭 {s['总分_关']} → 开启 **{s['总分_开']}**",
           f"- 维度得分标准差：{s['标准差_关']} → **{s['标准差_开']}**",
           f"- 档位分布（Q1/Q2/Q3/Q4）：关闭 {s['档位_关']} → 开启 **{s['档位_开']}**\n",
           "| 维度 | 满分 | 关闭锚点 | 开启锚点 | 差值 |", "|------|:---:|:---:|:---:|:---:|"]
    for r in s["维度明细"]:
        md.append(f"| {r['维度']} | {r['满分']} | {r['关锚点']} | {r['开锚点']} | {r['差值']:+} |")
    md.append("")

with open(f"{BASE}/output/anchors/ab_report.md", "w", encoding="utf-8") as f:
    f.write("\n".join(md))

log("A/B 完成")
print(json.dumps(report.get("汇总", {}), ensure_ascii=False, indent=1))
