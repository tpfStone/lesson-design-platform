# 汇总数学新增教案分数 + 重新盘点分布
import json, glob, os
from collections import defaultdict
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根目录
if BASE not in sys.path:
    sys.path.insert(0, BASE)

DIMS = ["教学内容", "教学理念", "学情分析", "教学目标", "教学资源", "教学方法",
        "过程设计", "课程思政", "课堂互动", "评价反馈", "版式观感", "文档规范"]

def norm(raw):
    if "数学" in raw: return "数学"
    if "英语" in raw or "PEP" in raw.upper(): return "英语"
    return raw

def band(s, full):
    r = s/full if full else 0
    if r < 0.25: return "Q1<25%"
    if r < 0.5: return "Q2 25-50%"
    if r < 0.75: return "Q3 50-75%"
    return "Q4 75-100%"

plans = {}
for f in glob.glob(f"{BASE}/output/competition/*/*_评分清单.json"):
    d = json.load(open(f, encoding="utf-8"))
    subj = norm(d.get("教案基本信息", {}).get("学科", ""))
    if subj != "数学":
        continue
    name = os.path.basename(os.path.dirname(f))
    plans[name] = d

print(f"数学 competition 共 {len(plans)} 份：\n")
# 新4份明细
new = ["不等式", "多位数", "年、月、日", "24时", "长方体"]
print("=== 新加入教案总分 ===")
for name, d in sorted(plans.items()):
    total = d.get("评分汇总", {}).get("总分")
    is_new = any(k in name for k in new)
    print(f"  [{'新' if is_new else '旧'}] {name[:24]}: {total}/100")

# 分布矩阵（数学 8 份）
print("\n=== 数学 8 份 × 维度档位分布 ===")
for dim in DIMS:
    counts = [0,0,0,0]
    lows = []
    for name, d in plans.items():
        for x in d.get("维度评分", []):
            if x["维度名称"] == dim:
                s, full = x.get("得分", 0), x.get("满分", 0)
                idx = 0 if s/full < .25 else 1 if s/full < .5 else 2 if s/full < .75 else 3
                counts[idx] += 1
                if idx <= 1:
                    lows.append(f"{name[:8]}:{s}/{full}")
    print(f"{dim:<6} Q1:{counts[0]} Q2:{counts[1]} Q3:{counts[2]} Q4:{counts[3]}  低分段: {' '.join(lows) if lows else '无'}")
