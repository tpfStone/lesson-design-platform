# 盘点现有竞赛标准产物在 数学/英语 各维度的得分分布
import json, glob, os
from collections import defaultdict
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根目录
if BASE not in sys.path:
    sys.path.insert(0, BASE)

DIMS = ["教学内容", "教学理念", "学情分析", "教学目标", "教学资源", "教学方法",
        "过程设计", "课程思政", "课堂互动", "评价反馈", "版式观感", "文档规范"]

def load_results(subjects=("数学", "英语")):
    results = defaultdict(list)  # subject -> [(plan, json)]
    for f in glob.glob(f"{BASE}/output/competition/*/*_评分清单.json"):
        d = json.load(open(f, encoding="utf-8"))
        info = d.get("教案基本信息", {})
        subj = info.get("学科", "")
        for s in subjects:
            if s in subj:
                plan = os.path.basename(os.path.dirname(f))
                results[s].append((plan, d))
                break
    return results

def band(score, full):
    """按满分比例的 4 档: 0-49%, 50-69%, 70-84%, 85-100%"""
    r = score / full if full else 0
    if r < 0.5: return "低(0-49%)"
    if r < 0.7: return "中低(50-69%)"
    if r < 0.85: return "中高(70-84%)"
    return "高(85-100%)"

res = load_results()
for subj, items in sorted(res.items()):
    print(f"\n{'='*60}\n{subj}（competition 标准，{len(items)} 份）")
    print(f"{'维度':<6}{'样本分':<34}{'覆盖档位'}")
    for dim in DIMS:
        scores = []
        for plan, d in items:
            for x in d.get("维度评分", []):
                if x["维度名称"] == dim:
                    scores.append((plan, x["得分"], x["满分"]))
        if not scores:
            print(f"{dim:<6} 无样本")
            continue
        bands = defaultdict(list)
        for plan, s, full in scores:
            bands[band(s, full)].append(f"{s}/{full}")
        cover = ", ".join(f"{b}:{len(v)}" for b, v in sorted(bands.items()))
        detail = " ".join(f"{p[:6]}:{s}/{f}" for p, s, f in scores)
        print(f"{dim:<6}{detail:<34}{cover}")

# 汇总缺口判断
print("\n" + "="*60)
print("各维度得分全览（原始）:")
for subj, items in sorted(res.items()):
    print(f"\n{subj}:")
    for plan, d in items:
        total = d.get("评分汇总", {}).get("总分")
        scores = {x["维度名称"]: f"{x['得分']}/{x['满分']}" for x in d.get("维度评分", [])}
        print(f"  {plan[:18]}: 总分{total} | " + " ".join(f"{k}={v}" for k, v in scores.items()))
