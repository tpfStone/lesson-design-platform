# 模拟用户 4 档规则：0-25% / 25-50% / 50-75% / 75-100%
# 现有 competition 数学4 + 英语4，看维度×档位覆盖矩阵
import json, glob, os
from collections import defaultdict
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根目录
if BASE not in sys.path:
    sys.path.insert(0, BASE)

DIMS = ["教学内容", "教学理念", "学情分析", "教学目标", "教学资源", "教学方法",
        "过程设计", "课程思政", "课堂互动", "评价反馈", "版式观感", "文档规范"]
BANDS = ["Q1:0-25%", "Q2:25-50%", "Q3:50-75%", "Q4:75-100%"]

def band_idx(score, full):
    r = score / full if full else 0
    # 边界规则: 0.25/0.5/0.75 归入低一档的上一档？统一用 < 判断: 25%归Q1? 
    # 采用：r < 0.25 → Q1; < 0.5 → Q2; < 0.75 → Q3; else Q4
    if r < 0.25: return 0
    if r < 0.5: return 1
    if r < 0.75: return 2
    return 3

def load(subjects=("数学", "英语")):
    res = defaultdict(list)
    for f in glob.glob(f"{BASE}/output/competition/*/*_评分清单.json"):
        d = json.load(open(f, encoding="utf-8"))
        raw = d.get("教案基本信息", {}).get("学科", "")
        subj = "数学" if "数学" in raw else ("英语" if ("英语" in raw or "PEP" in raw.upper()) else None)
        if subj in subjects:
            res[subj].append((os.path.basename(os.path.dirname(f)), d))
    return res

res = load()
print("档位边界规则: 得分/满分 < 25%→Q1, <50%→Q2, <75%→Q3, 其余→Q4\n")

for subj, items in sorted(res.items()):
    print(f"{'='*66}\n{subj}（{len(items)} 份）— 维度 × 档位 样本数矩阵")
    print(f"{'维度':<6}" + "".join(f"{b:>10}" for b in BANDS) + f"{'覆盖档数':>8}")
    empty_dims = 0
    for dim in DIMS:
        counts = [0, 0, 0, 0]
        for plan, d in items:
            for x in d.get("维度评分", []):
                if x["维度名称"] == dim:
                    counts[band_idx(x["得分"], x["满分"])] += 1
        covered = sum(1 for c in counts if c > 0)
        if covered < 4: empty_dims += 1
        flag = "  ←缺档" if covered < 4 else ""
        print(f"{dim:<6}" + "".join(f"{c:>10}" for c in counts) + f"{covered:>8}{flag}")
    print(f"缺档维度数: {empty_dims}/12")

# 每档各维度的原始样本（看能不能满足每档2-3个）
print("\n" + "="*66)
print("各档位现有哪些维度的样本（教案简称:分/满分）")
for subj, items in sorted(res.items()):
    print(f"\n{subj}:")
    for b in range(4):
        samples = []
        for plan, d in items:
            p = plan[:8]
            for x in d.get("维度评分", []):
                if band_idx(x["得分"], x["满分"]) == b:
                    samples.append(f"{p}:{x['维度名称']}={x['得分']}/{x['满分']}")
        print(f"  {BANDS[b]}: {len(samples)} 个 | " + " ".join(samples[:24]))
