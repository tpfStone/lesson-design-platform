# 粗评数据维度区分度分析（competition 数学9 + 英语11）
import json, glob, os
from collections import defaultdict
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根目录
if BASE not in sys.path:
    sys.path.insert(0, BASE)

DIMS = ["教学内容", "教学理念", "学情分析", "教学目标", "教学资源", "教学方法",
        "过程设计", "课程思政", "课堂互动", "评价反馈", "版式观感", "文档规范"]
# 各维满分
FULL = {"教学内容": 10, "教学理念": 5, "学情分析": 5, "教学目标": 5, "教学资源": 10,
        "教学方法": 10, "过程设计": 20, "课程思政": 5, "课堂互动": 10, "评价反馈": 10,
        "版式观感": 5, "文档规范": 5}

def norm(raw):
    if "数学" in raw: return "数学"
    if "英语" in raw or "PEP" in raw.upper(): return "英语"
    return None

def stats(values):
    """均值/标准差/范围，值已按满分归一化 0-1"""
    n = len(values)
    if n == 0: return None
    m = sum(values) / n
    var = sum((v - m) ** 2 for v in values) / n
    sd = var ** 0.5
    return m, sd, min(values), max(values)

def coverage(dim):
    """实际占据的档数（归一化 0-1 分 4 档看分布是否集中）"""
    pass

# 收集每学科每维度 得分/满分
data = defaultdict(lambda: defaultdict(list))
plans = []
for f in glob.glob(f"{BASE}/output/competition/*/*_评分清单.json"):
    d = json.load(open(f, encoding="utf-8"))
    subj = norm(d.get("教案基本信息", {}).get("学科", ""))
    if subj not in ("数学", "英语"):
        continue
    name = os.path.basename(os.path.dirname(f))
    plans.append((subj, name, d))
    for x in d.get("维度评分", []):
        dim = x["维度名称"]
        full = x.get("满分", 0)
        if full:
            data[subj][dim].append(x.get("得分", 0) / full)

print(f"样本: 数学 {sum(1 for s,_,_ in plans if s=='数学')} 份, 英语 {sum(1 for s,_,_ in plans if s=='英语')} 份\n")

print("=" * 100)
print(f"{'维度':<6}{'满分':<5}{'学科':<5}{'均值%':<8}{'标准差':<8}{'范围%':<16}{'区分度评':<8}")
print("-" * 100)
for dim in DIMS:
    for subj in ("数学", "英语"):
        vals = data[subj][dim]
        st = stats(vals)
        if not st:
            continue
        m, sd, lo, hi = st
        span = (hi - lo) * 100
        # 区分度评级：sd<0.1 弱；0.1-0.2 中；>0.2 强
        level = "强" if sd > 0.2 else ("中" if sd > 0.1 else "弱")
        print(f"{dim:<6}{FULL.get(dim,''):<5}{subj:<5}{m*100:<8.0f}{sd:<8.3f}{lo*100:.0f}-{hi*100:.0f}%({span:.0f}pt){'':<4}{level}")
    print()

# 汇总：5分维度 vs 10+分维度区分度
print("=" * 100)
print("区分度汇总（两科平均）")
small = [dim for dim in DIMS if FULL[dim] <= 5]
big = [dim for dim in DIMS if FULL[dim] >= 10]
for label, grp in [("5分维度", small), ("10分+维度", big)]:
    sds = []
    for dim in grp:
        for subj in ("数学", "英语"):
            st = stats(data[subj][dim])
            if st: sds.append(st[1])
    print(f"{label}: 平均标准差 = {sum(sds)/len(sds):.3f} (N={len(sds)})")

# 5分维度实际得分分布（看压缩情况）
print("\n5分维度实际得分分布（数学+英语合并，归一化*5取整）:")
for dim in small:
    allv = []
    for subj in ("数学", "英语"):
        allv += [v * 5 for v in data[subj][dim]]
    dist = defaultdict(int)
    for v in allv:
        dist[round(v)] += 1
    spread = sorted(dist.items())
    print(f"  {dim:<5} N={len(allv)}: " + " ".join(f"{k}分:{c}" for k, c in spread))
