"""
============================================================
教案智能批注系统 — 本地 Web 界面（Streamlit）
启动：streamlit run web/app.py   （或双击 start_web.bat）
============================================================
页面：
  ① 首页 · 环境自检
  ② 教案评分
  ③ 复核标注（人工定标）
  ④ 批量与对比
  ⑤ 设置
"""

import os
import sys
import json
import time
import shutil
from datetime import datetime

import streamlit as st

# 项目根目录加入 sys.path
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

st.set_page_config(
    page_title="教案智能批注系统",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded",
)

DIMS_ORDER = ["教学内容", "教学理念", "学情分析", "教学目标", "教学资源", "教学方法",
              "过程设计", "课程思政", "课堂互动", "评价反馈", "版式观感", "文档规范",
              "结构完整"]


# ============================================================
# 基础工具
# ============================================================

@st.cache_resource
def get_config():
    from pipeline import load_config
    return load_config(os.path.join(BASE, "config.yaml"))


def cfg():
    return get_config()


# ============================================================
# API Key（交付版：设置页填写并保存到本地文件，重启后依然有效）
# ============================================================

def key_status():
    """统一的 Key 状态查询（含来源与脱敏），供各处显示"""
    from providers import get_key_status
    return get_key_status(cfg().get("api_keys", {}).get("deepseek", ""))


def to_number(x):
    """
    把用户输入/系统值安全地转成 float。
    None、空字符串、NaN、非法值一律返回 None（避免抛异常）。
    容忍带单位的输入（如 "8分"、"7.5 分"）。
    """
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        f = float(x)
        return None if f != f else f          # 过滤 NaN
    s = str(x).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        import re as _re
        m = _re.search(r"-?\d+(?:\.\d+)?", s)
        return float(m.group(0)) if m else None


def render_sidebar():
    st.sidebar.title("📝 教案智能批注")
    st.sidebar.caption("标注示例驱动的 Few-Shot 评分系统")
    page = st.sidebar.radio("功能导航", [
        "🏠 首页 · 环境自检",
        "📝 教案评分",
        "🔍 复核标注",
        "📊 批量与对比",
        "⚙️ 设置",
    ])
    st.sidebar.divider()
    # Key 状态（三级来源：本地保存 > config.yaml > 环境变量）
    ks = key_status()
    if ks["configured"]:
        st.sidebar.success(f"API Key 已配置（{ks['masked']}）\n\n来源：{ks['source']}")
    else:
        st.sidebar.error("API Key 未配置\n\n请到「⚙️ 设置」页填写")
    m = cfg().get("llm", {})
    st.sidebar.info(f"模型：{m.get('model', '?')}\n\n温度：{m.get('temperature', 0.1)}")
    a = cfg().get("anchors", {}) or {}
    st.sidebar.caption(f"锚点注入：{'开' if a.get('enabled', True) else '关'}（{a.get('mode', 'both')}）")
    return page


def kb_status():
    """知识库状态"""
    from standards import _load as _load_std
    from suggester import _load_methods
    from knowledge_base import load_knowledge_base
    out = {}
    try:
        out["设计理论库"] = len(load_knowledge_base() or [])
    except Exception:
        out["设计理论库"] = 0
    for subj in ("数学", "英语"):
        try:
            out[f"{subj}课标"] = len(_load_std(subj) or [])
        except Exception:
            out[f"{subj}课标"] = 0
        try:
            out[f"{subj}教学法"] = len(_load_methods(subj) or [])
        except Exception:
            out[f"{subj}教学法"] = 0
    from anchors import get_anchor_stats
    for subj, s in get_anchor_stats().items():
        out[f"{subj}锚点"] = f"{s['档位条目']} 档位 / {s['含模板']} 含示例"
    return out


def load_plan_result(criteria, plan_base):
    """读取某教案的评分清单 JSON"""
    path = os.path.join(BASE, "output", criteria, plan_base, f"{plan_base}_评分清单.json")
    if not os.path.exists(path):
        return None, None
    with open(path, encoding="utf-8") as f:
        return json.load(f), path


def list_all_results():
    """列出所有已评分结果 (标准, 教案名)"""
    items = []
    root = os.path.join(BASE, "output")
    for criteria in ("competition", "student"):
        d = os.path.join(root, criteria)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            p = os.path.join(d, name)
            if os.path.isdir(p) and any(x.endswith("_评分清单.json") for x in os.listdir(p)):
                items.append((criteria, name))
    return items


# ============================================================
# 页面 1：首页 · 环境自检
# ============================================================

def page_home():
    st.title("🏠 教案智能批注系统")
    st.caption("基于标注示例（Few-Shot）+ 课标知识库 + 教学法库 + 分数段锚点的教案评分与批注工具")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("① 准备")
        st.markdown("""
- 把**教案**放进 `data/plans/`
- 把**评分标准**放进 `data/criteria/`
- 在「⚙️ 设置」里填写 **API Key**
""")
    with c2:
        st.subheader("② 评分")
        st.markdown("""
- 打开「📝 教案评分」
- 选择教案与标准 → 开始评分
- 约 2 分钟/份（含批注生成）
""")
    with c3:
        st.subheader("③ 复核")
        st.markdown("""
- 打开「🔍 复核标注」
- 逐条核对系统评分，填写复核分
- 导出定标数据（JSON/CSV）
""")

    st.divider()
    st.subheader("环境自检")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("**依赖检查**")
        mods = [("streamlit", "界面"), ("fitz", "PDF 解析"), ("docx", "Word 报告"),
                ("openpyxl", "Excel"), ("yaml", "配置"), ("openai", "LLM 接口"),
                ("easyocr", "扫描版 OCR（可选）")]
        rows = []
        for mod, desc in mods:
            try:
                __import__(mod)
                rows.append({"依赖": mod, "用途": desc, "状态": "✅ 已安装"})
            except ImportError:
                rows.append({"依赖": mod, "用途": desc, "状态": "❌ 缺失"})
        st.dataframe(rows, hide_index=True, width="stretch")

    with col2:
        st.markdown("**知识库状态**")
        st.dataframe([{"知识库": k, "条目数": str(v)} for k, v in kb_status().items()],
                     hide_index=True, width="stretch")

    st.markdown("**数据目录**")
    from service import list_resources
    res = list_resources(BASE, cfg())
    d1, d2, d3 = st.columns(3)
    d1.metric("待评教案", f"{len(res['plans'])} 份")
    d2.metric("评分标准", f"{len(res['criteria'])} 个")
    d3.metric("标注示例", f"{len(res['examples'])} 份")

    with st.expander("API Key 检测"):
        ks = key_status()
        if ks["configured"]:
            st.success(f"已配置（{ks['masked']}）　来源：{ks['source']}")
        else:
            st.error("未检测到 API Key")
            st.markdown(
                "**怎么配置？**\n"
                "1. 左侧菜单进入「⚙️ 设置」\n"
                "2. 把 DeepSeek API Key 粘贴到输入框，点「💾 保存」\n"
                "3. 保存后会写入项目内的 `data/.api_key`，下次启动不用再填\n\n"
                "> 还没有 Key？到 https://platform.deepseek.com 注册后在「API Keys」页创建。"
            )


# ============================================================
# 页面 2：教案评分
# ============================================================

def page_score():
    st.title("📝 教案评分")
    from service import run_annotation, AnnotationError, list_resources

    res = list_resources(BASE, cfg())

    # --- 选择教案 ---
    st.subheader("1️⃣ 选择教案")
    source = st.radio("教案来源", ["从数据目录选择", "上传新文件"], horizontal=True)
    plan_name = None

    if source == "从数据目录选择":
        if res["plans"]:
            plan_name = st.selectbox("待评教案", res["plans"])
        else:
            st.warning("data/plans/ 下没有教案，请先放入教案文件或使用上传功能")
    else:
        up = st.file_uploader("上传教案（PDF / DOCX；扫描版 PDF 会自动 OCR，耗时较长）",
                              type=["pdf", "docx"])
        if up is not None:
            up_dir = os.path.join(BASE, "data", "plans", "uploads")
            os.makedirs(up_dir, exist_ok=True)
            dst = os.path.join(up_dir, up.name)
            with open(dst, "wb") as f:
                f.write(up.getbuffer())
            plan_name = os.path.join("uploads", up.name)
            st.success(f"已保存：{dst}")

    # --- 扫描版 PDF 前置提示（避免用户看到技术性报错）---
    ocr_blocked = False
    if plan_name:
        try:
            from parsers import is_scanned_pdf, ocr_available
            _p = os.path.join(BASE, "data", "plans", plan_name)
            if os.path.exists(_p) and is_scanned_pdf(_p) and not ocr_available():
                ocr_blocked = True
                st.warning(
                    "⚠️ **这份 PDF 是扫描版**（整页图片、没有文字层），需要先安装 OCR 组件才能评分。\n\n"
                    "**安装方法**（二选一）：\n"
                    "- 双击 `tools\\install_ocr.bat`（约 2GB，需 5-20 分钟）\n"
                    "- 或命令行执行：`python -m pip install easyocr -i https://pypi.tuna.tsinghua.edu.cn/simple`\n\n"
                    "详细步骤见 **`docs\\OCR安装与使用说明.md`**\n\n"
                    "💡 如果手上有 **Word 版**或**文字版 PDF**，可直接用它们评分（无需 OCR）。"
                )
        except Exception:
            pass

    # --- 参数 ---
    # 2026-10-04：按课题组要求，评分标准与提示词固定为「学生标准 + v2」，界面不再提供选项
    st.subheader("2️⃣ 评分设置")
    criteria = "student"        # 固定：学生标准
    variant = "v2_guided"       # 固定：v2 引导流程
    c1, c2 = st.columns([2, 2])
    c1.info("评分标准：**学生标准**（固定）")
    c2.info("评审方式：**v2 引导流程**（固定）")
    suggest = st.checkbox("生成细化建议", value=True, help="额外 1 次 LLM 调用，约 +40 秒")

    dry = st.checkbox("Dry Run（只生成提示词，不调用模型）", value=False)

    if st.button("🚀 开始评分", type="primary", disabled=(not plan_name) or ocr_blocked):
        if not key_status()["configured"] and not dry:
            st.error("未配置 API Key，请到「⚙️ 设置」页面填写并保存")
            return

        logs = []
        status = st.status("正在评分…", expanded=True)
        box = status.empty()

        def cb(msg):
            logs.append(msg)
            box.write(f"· {msg}")

        t0 = time.time()
        try:
            out = run_annotation(
                base_dir=BASE, config=cfg(), plan_filename=plan_name,
                criteria_type=criteria, variant=variant,
                suggest=suggest, dry_run=dry, progress=cb,
            )
            status.update(label=f"✅ 完成（{time.time()-t0:.0f} 秒）", state="complete")
            if out.get("result"):
                st.session_state["last_result"] = out
        except AnnotationError as e:
            status.update(label="❌ 失败", state="error")
            st.error(str(e))
            return
        except Exception as e:
            status.update(label="❌ 异常", state="error")
            st.exception(e)
            return

    # --- 结果展示 ---
    out = st.session_state.get("last_result")
    if out and out.get("result"):
        r = out["result"]
        st.divider()
        st.subheader("3️⃣ 评分结果")

        total = r.get("评分汇总", {}).get("总分")
        dim_max = sum(d.get("满分", 0) for d in r.get("维度评分", []))
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("总分", f"{total} / {dim_max or 100}")
        m2.metric("学科", out.get("subject") or "—")
        m3.metric("年级", out.get("grade") or "—")
        m4.metric("耗时", f"{out.get('elapsed', 0):.0f} 秒")

        st.markdown("**总体评价**")
        st.info(r.get("总体评价", ""))

        # 一级维度汇总（2026-10-04：按学生标准的一级维度分组展示）
        try:
            from standards import group_by_level1, get_level1
            _groups = group_by_level1(r.get("维度评分", []))
        except Exception:
            _groups = []
            def get_level1(_x):
                return ""

        if _groups:
            st.markdown("**一级维度得分**（一级维度不评等级；其下二级维度标注 A/B/C）")
            g_rows = []
            for g in _groups:
                g_rows.append({
                    "一级维度": g["一级维度"],
                    "满分": g["满分"],
                    "得分": g["得分"],
                    "含二级维度（得分/满分·等级）": "、".join(
                        f"{d.get('维度名称','')}({d.get('得分')}/{d.get('满分')}·{d.get('等级','')})"
                        for d in g["维度列表"]),
                })
            st.dataframe(g_rows, hide_index=True, width="stretch")

        # 维度得分表（二级维度，含等级）
        rows = []
        for d in r.get("维度评分", []):
            cnt = len(d.get("批注列表", []))
            _sc, _fl = to_number(d.get("得分")), to_number(d.get("满分"))
            rows.append({
                "一级维度": get_level1(d.get("维度名称", "")),
                "维度": d.get("维度名称"),
                "满分": d.get("满分"),
                "得分": d.get("得分"),
                "等级": d.get("等级", ""),
                "得分率": f"{(_sc / _fl * 100):.0f}%" if (_sc is not None and _fl) else "—",
                "批注数": cnt,
                "得分理由": (d.get("得分理由") or "")[:60],
            })
        st.dataframe(rows, hide_index=True, width="stretch")

        # 维度得分条形图
        chart_data = {r["维度"]: r["得分"] for r in rows}
        st.bar_chart(chart_data, height=260)

        # 批注明细
        st.markdown("**批注明细**")
        for d in r.get("维度评分", []):
            anns = d.get("批注列表", [])
            if not anns:
                continue
            with st.expander(f"{d['维度名称']} · {d.get('得分')}/{d.get('满分')} · {len(anns)} 条批注"):
                for i, a in enumerate(anns, 1):
                    st.markdown(f"**{i}. [{a.get('评价', '')}]** {a.get('位置', '')}")
                    if a.get("原文引用"):
                        st.caption(f"原文：{a['原文引用']}")
                    if a.get("具体分析"):
                        st.markdown(f"- 分析：{a['具体分析']}")
                    if a.get("建议"):
                        st.markdown(f"- 诊断：{a['建议']}")
                    if a.get("依据来源"):
                        st.markdown(f"- 📚 依据来源：{a['依据来源']}")
                    if a.get("教学法参考"):
                        st.markdown(f"- 🏫 教学法参考：{a['教学法参考']}")
                    if a.get("细化建议"):
                        st.markdown(f"- 💡 细化建议：{a['细化建议']}")
                    st.divider()

        # 下载
        st.markdown("**下载产物**")
        files = out.get("files", {})
        labels = {"docx": "批注报告 DOCX", "pdf": "已批注 PDF", "json": "评分清单 JSON",
                  "md": "评分清单 MD", "docx_annotated": "已批注 Word（批注气泡）"}
        cols = st.columns(len(files) or 1)
        for i, (k, p) in enumerate(files.items()):
            if os.path.exists(p):
                with open(p, "rb") as f:
                    cols[i % len(cols)].download_button(
                        labels.get(k, k), f.read(),
                        file_name=os.path.basename(p), key=f"dl_{k}",
                    )


# ============================================================
# 页面 3：复核标注
# ============================================================

def page_review():
    st.title("🔍 复核标注")
    st.caption("逐条核对系统评分，填写复核分与意见 —— 用于研究生人工定标、校准系统评分")

    items = list_all_results()
    if not items:
        st.warning("还没有评分结果，请先到「📝 教案评分」跑一份教案")
        return

    c1, c2 = st.columns([1, 2])
    with c1:
        pair = st.selectbox(
            "选择评分结果",
            items,
            format_func=lambda x: f"{'竞赛' if x[0]=='competition' else '学生'} ｜ {x[1]}",
        )
    data, path = load_plan_result(pair[0], pair[1])
    if not data:
        st.error("读取评分清单失败")
        return

    with c2:
        total = data.get("评分汇总", {}).get("总分")
        dim_max = sum(d.get("满分", 0) for d in data.get("维度评分", []))
        st.metric("系统总分", f"{total} / {dim_max or 100}")

    with st.expander("总体评价"):
        st.write(data.get("总体评价", ""))

    st.subheader("维度级复核")
    st.caption("修改「复核得分」列即可；留空表示认可系统分")

    dim_rows = []
    for d in data.get("维度评分", []):
        dim_rows.append({
            "维度": d.get("维度名称"),
            "满分": d.get("满分"),
            "系统得分": d.get("得分"),
            "复核得分": None,
            "复核意见": "",
        })
    edited = st.data_editor(dim_rows, hide_index=True, width="stretch",
                            key=f"dim_editor_{pair[0]}_{pair[1]}")

    st.subheader("批注级复核")
    st.caption("可修正评价等级（优秀/达标/基本达标/部分达标/未达标）")

    ann_rows = []
    idx = 0
    for d in data.get("维度评分", []):
        for a in d.get("批注列表", []):
            idx += 1
            ann_rows.append({
                "编号": idx,
                "维度": d.get("维度名称"),
                "位置": (a.get("位置") or "")[:24],
                "原文引用": (a.get("原文引用") or "")[:40],
                "系统评价": a.get("评价", ""),
                "复核评价": a.get("评价", ""),
                "复核备注": "",
            })
    edited_anns = st.data_editor(ann_rows, hide_index=True, width="stretch",
                                 key=f"ann_editor_{pair[0]}_{pair[1]}", height=340)

    st.divider()
    col1, col2 = st.columns([1, 3])
    if col1.button("💾 保存复核结果", type="primary"):
        reviewer = st.session_state.get("reviewer_name", "reviewer")
        review = {
            "教案": pair[1],
            "标准": pair[0],
            "复核人": reviewer,
            "复核时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "系统总分": data.get("评分汇总", {}).get("总分"),
            "维度复核": edited,
            "批注复核": edited_anns,
        }
        # 差异统计（兼容用户输入为字符串/空值/带单位等情况，避免类型错误）
        diffs = []
        for r in edited:
            v = to_number(r.get("复核得分"))
            if v is None:                      # 留空 = 认可系统分，跳过
                continue
            diffs.append((r.get("维度"), to_number(r.get("系统得分")), v))
        review["维度差异"] = [
            {"维度": d,
             "系统": s,
             "复核": v,
             "差": round(v - s, 2) if s is not None else None}
            for d, s, v in diffs
        ]
        out_dir = os.path.join(BASE, "output", "review")
        os.makedirs(out_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(out_dir, f"{pair[1][:30]}_{pair[0]}_{stamp}_复核.json")
        _review_json = json.dumps(review, ensure_ascii=False, indent=1)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(_review_json)
        st.success(f"已保存：{out_path}")

        # 2026-10-04：保存后直接提供下载（对应反馈问题 10：不用再去文件夹里找）
        st.download_button(
            "⬇️ 下载复核结果（JSON）",
            data=_review_json,
            file_name=os.path.basename(out_path),
            mime="application/json",
            key=f"dl_review_{stamp}",
            type="primary",
        )

        if diffs:
            st.markdown("**复核差异**")
            st.dataframe(review["维度差异"], hide_index=True, width="stretch")

    with col2:
        st.caption("复核结果保存在 `output/review/`，可用于统计系统分与人工分的差异、校准评分尺度。")


# ============================================================
# 页面 4：批量与对比
# ============================================================

def build_radar_chart(data: list, dims: list, show_values: bool = True):
    """
    雷达图（ECharts / Excel 经典样式）。2026-10-04。

    样式特征：
      · 多层多边形网格（5 层）+ 各维度轴线
      · 轴上标刻度值（0-100）
      · 每个系列 = 折线 + 实心圆点（**无填充**）
      · 可选：在每个数据点旁直接标注数值
      · 归一化得分率（得分÷满分×100），使满分不同的维度可同图比较

    data: [{"教案": 名称, "维度": 维度名, "得分率": 数值(0-100)}, ...]
    dims: 维度顺序列表
    show_values: 是否在每个数据点旁标注数值
    """
    import math
    import pandas as pd
    import altair as alt

    n = len(dims)
    if n < 3:
        return None
    ang = {d: 2 * math.pi * i / n for i, d in enumerate(dims)}
    names = list(dict.fromkeys(x["教案"] for x in data))

    # ---- 数据点（含闭合点）----
    rows = []
    for nm in names:
        by = {x["维度"]: x["得分率"] for x in data if x["教案"] == nm}
        for d in dims:
            v = by.get(d, 0)
            rows.append({"教案": nm, "维度": d, "得分率": v,
                         "x": v * math.cos(ang[d]), "y": v * math.sin(ang[d]),
                         "角度": math.degrees(ang[d])})
        d0 = dims[0]
        v0 = by.get(d0, 0)
        rows.append({"教案": nm, "维度": d0, "得分率": v0,
                     "x": v0 * math.cos(ang[d0]), "y": v0 * math.sin(ang[d0]), "角度": 360.0})
    df = pd.DataFrame(rows)

    # ---- 网格：5 层同心多边形（20/40/60/80/100）----
    #      每圈生成 n+1 个点（末点回到首点）形成闭合；额外记录「秩」用于指定连线顺序 —— 
    #      Vega-Lite 的 line 若缺少 order 会按 x 排序，导致多边形顶点顺序错乱、画不闭合。
    grid = []
    for r in (20, 40, 60, 80, 100):
        for i in range(n + 1):
            a = 2 * math.pi * (i % n) / n
            grid.append({"x": r * math.cos(a), "y": r * math.sin(a),
                         "圈": str(r), "秩": i})
    gdf = pd.DataFrame(grid)
    g_inner = gdf[gdf["圈"] != "100"]
    g_outer = gdf[gdf["圈"] == "100"]

    # ---- 轴线 + 外圈维度标签 ----
    axis_rows = []
    for i, d in enumerate(dims):
        a = 2 * math.pi * i / n
        axis_rows.append({"x": 100 * math.cos(a), "y": 100 * math.sin(a),
                          "x2": 0, "y2": 0,
                          "lx": 115 * math.cos(a), "ly": 115 * math.sin(a), "维度": d})
    adf = pd.DataFrame(axis_rows)

    # ---- 轴刻度值（标在正上方那根轴上）----
    tdf = pd.DataFrame([{"tx": 3.0, "ty": r, "sc": r} for r in (20, 40, 60, 80, 100)])

    def xy():
        return (alt.X("x:Q", axis=None, scale=alt.Scale(domain=[-128, 128])),
                alt.Y("y:Q", axis=None, scale=alt.Scale(domain=[-128, 128])))

    x1, y1 = xy()
    grid_inner_chart = alt.Chart(g_inner).mark_line(color="#E6E6E6", strokeWidth=1).encode(
        x=x1, y=y1, detail=alt.Detail("圈:N"), order=alt.Order("秩:Q"))

    x1b, y1b = xy()
    grid_outer_chart = alt.Chart(g_outer).mark_line(color="#BFBFBF", strokeWidth=1.3).encode(
        x=x1b, y=y1b, order=alt.Order("秩:Q"))

    x2, y2 = xy()
    axis_chart = alt.Chart(adf).mark_rule(color="#DCDCDC", strokeWidth=1).encode(
        x=x2, y=y2, x2="x2:Q", y2="y2:Q")

    x3, y3 = xy()
    label_chart = alt.Chart(adf).mark_text(fontSize=12, color="#333333", align="center").encode(
        x=x3, y=y3, text="维度:N")

    x4, y4 = xy()
    tick_chart = alt.Chart(tdf).mark_text(fontSize=9, color="#AAAAAA", align="left").encode(
        x=alt.X("tx:Q", axis=None, scale=alt.Scale(domain=[-124, 124])),
        y=alt.Y("ty:Q", axis=None, scale=alt.Scale(domain=[-124, 124])),
        text=alt.Text("sc:Q", format=".0f"))

    color = alt.Color("教案:N", legend=alt.Legend(orient="bottom", columns=3, title=None),
                      scale=alt.Scale(scheme="tableau10"))

    x5, y5 = xy()
    line_chart = alt.Chart(df).mark_line(
        strokeWidth=2, opacity=0.95,
        point=alt.OverlayMarkDef(size=55, filled=True, strokeWidth=0, opacity=1.0),
    ).encode(
        x=x5, y=y5, color=color, order=alt.Order("角度:Q"),
        tooltip=["教案:N", "维度:N", "得分率:Q"])

    layers = [grid_inner_chart, grid_outer_chart, axis_chart, label_chart, tick_chart]
    if show_values:
        x6, y6 = xy()
        value_chart = alt.Chart(df).mark_text(fontSize=9, dy=-10, color="#555555").encode(
            x=x6, y=y6, text=alt.Text("得分率:Q", format=".0f"))
        layers.append(value_chart)
    layers.append(line_chart)

    chart = layers[0]
    for l in layers[1:]:
        chart = chart + l
    # 固定为正方形尺寸：雷达图依赖等比例坐标轴，宽度/高度不一致会被拉扁变形。
    # 尺寸取 620：在全屏宽度下也足够大、界面更协调（渲染处会居中显示）。
    _side = 620
    return chart.properties(width=_side, height=_side)



def page_batch():
    st.title("📊 批量与对比")
    from service import run_batch, list_resources

    res = list_resources(BASE, cfg())
    tab1, tab2 = st.tabs(["批量评分", "结果对比"])

    with tab1:
        # 2026-10-04：批量上传（对应反馈问题 12：教师不必手动往 data/plans 里放文件）
        with st.expander("📤 批量上传教案（可一次选多个文件）", expanded=False):
            ups = st.file_uploader(
                "选择教案文件（支持 PDF / DOCX，可多选）",
                type=["pdf", "docx"],
                accept_multiple_files=True,
                key="batch_uploader",
                help="若手上是 .doc 旧格式，请先用 Word 另存为 .docx 再上传",
            )
            if ups:
                st.caption(f"已选择 {len(ups)} 个文件："
                           + "、".join(u.name[:26] for u in ups[:4])
                           + ("…" if len(ups) > 4 else ""))
                if st.button(f"⬆️ 导入这 {len(ups)} 个文件", type="primary"):
                    dst_dir = os.path.join(BASE, "data", "plans")
                    os.makedirs(dst_dir, exist_ok=True)
                    saved, renamed = 0, []
                    for u in ups:
                        target = os.path.join(dst_dir, u.name)
                        if os.path.exists(target):          # 重名自动加序号
                            stem, ext = os.path.splitext(u.name)
                            i = 1
                            while os.path.exists(os.path.join(dst_dir, f"{stem}_{i}{ext}")):
                                i += 1
                            target = os.path.join(dst_dir, f"{stem}_{i}{ext}")
                            renamed.append(os.path.basename(target))
                        with open(target, "wb") as f:
                            f.write(u.getbuffer())
                        saved += 1
                    msg = f"✅ 已导入 {saved} 个文件到 `data/plans/`"
                    if renamed:
                        msg += f"（{len(renamed)} 个同名文件已自动加序号）"
                    st.success(msg)
                    st.info("请在下方「选择要评分的教案」中勾选它们，然后开始批量评分。")
                    st.rerun()

        # 2026-10-04：批量评分同样固定为「学生标准 + v2」
        criteria = "student"
        variant = "v2_guided"
        plans = st.multiselect("选择要评分的教案", res["plans"])
        if plans:
            st.caption("评分标准：**学生标准**（固定）｜评审方式：**v2 引导流程**（固定）")

            # 扫描版 PDF 预检（对应反馈问题 13：批量上传 PDF 评分失败）
            try:
                from parsers import is_scanned_pdf, ocr_available
                _has_ocr = ocr_available()
                _scanned = []
                for _p in plans:
                    _full = os.path.join(BASE, "data", "plans", _p)
                    if os.path.exists(_full) and is_scanned_pdf(_full):
                        _scanned.append(_p)
                if _scanned and not _has_ocr:
                    st.warning(
                        f"⚠️ 选中的 {len(_scanned)} 份为**扫描版 PDF**，当前未安装 OCR 组件，这些会评分失败：\n\n"
                        + "\n".join(f"- {n}" for n in _scanned[:5])
                        + ("\n- …" if len(_scanned) > 5 else "")
                        + "\n\n**安装方法**：双击 `tools\\install_ocr.bat`，"
                          "或查看 `docs\\OCR安装与使用说明.md`（约 2GB，5-20 分钟）"
                    )
                elif _scanned and _has_ocr:
                    st.info(f"ℹ️ 选中的 {len(_scanned)} 份为扫描版 PDF，将使用 OCR 识别（单份约 5-10 分钟，明显慢于普通教案）")
            except Exception:
                pass

            if st.button("🚀 开始批量评分", type="primary"):
                logs = []
                status = st.status(f"批量评分中（{len(plans)} 份）…", expanded=True)
                box = status.empty()
                prog = st.progress(0.0)

                done = {"n": 0}

                def cb(msg):
                    logs.append(msg)
                    box.write(f"· {msg}")
                    if msg.startswith("["):
                        try:
                            done["n"] = int(msg.split("]")[0].strip("[").split("/")[0])
                            prog.progress(min(done["n"] / len(plans), 1.0))
                        except Exception:
                            pass

                # 单份执行以获得可控进度显示
                from service import run_annotation, AnnotationError
                ok, fail = 0, 0
                for i, p in enumerate(plans, 1):
                    box.write(f"**[{i}/{len(plans)}] {p}**")
                    try:
                        run_annotation(BASE, cfg(), p, criteria, variant, suggest=True, progress=cb)
                        ok += 1
                    except Exception as e:
                        fail += 1
                        box.write(f"❌ {p} 失败：{e}")
                    prog.progress(i / len(plans))
                status.update(label=f"✅ 批量完成（成功 {ok}，失败 {fail}）", state="complete")

    with tab2:
        items = list_all_results()
        if not items:
            st.info("暂无评分结果")
            return
        rows = []
        for criteria, name in items:
            d, _ = load_plan_result(criteria, name)
            if not d:
                continue
            rows.append({
                "标准": "竞赛" if criteria == "competition" else "学生",
                "教案": name,
                "总分": d.get("评分汇总", {}).get("总分"),
                "学科": d.get("教案基本信息", {}).get("学科", ""),
                "年级": d.get("教案基本信息", {}).get("年级", ""),
            })
        st.dataframe(rows, hide_index=True, width="stretch")

        st.divider()
        st.subheader("结果对比")

        # 2026-10-04：自选教案（对应反馈问题 14）
        labels = [f"{'竞赛' if c == 'competition' else '学生'} ｜ {n}" for c, n in items]
        # 默认优先勾选「同一标准」（优先学生标准）的前 5 份，避免不同标准的分数混合比较
        _same = [i for i, (c, _n) in enumerate(items) if c == "student"]
        if not _same:
            _same = list(range(len(items)))
        default = [labels[i] for i in _same[:5]]
        picked = st.multiselect(
            "选择要对比的教案",
            options=labels, default=default, key="cmp_pick",
            help="雷达图建议不超过 5 份，否则线条难以辨认；不同评分标准的分数不可直接比较")
        if not picked:
            st.info("请至少勾选 1 份教案")
            return
        sel = [(c, n) for (c, n), lab in zip(items, labels) if lab in picked]
        st.caption(f"将对比 **{len(sel)}** 份教案")
        if len({c for c, _ in sel}) > 1:
            st.warning("所选教案包含**不同评分标准**（竞赛 / 学生），两套标准的满分体系与分数尺度不同，"
                       "横向对比仅供参考 —— 建议只勾选同一标准的教案。")

        # 视图切换：表格 / 雷达图（雷达图用归一化得分率）
        view = st.radio("展示方式", ["📋 横向对比表（表格）", "🕸️ 维度雷达图"],
                        horizontal=True, key="cmp_view")

        if view.startswith("📋"):
            if st.button("🔁 生成横向对比表", type="primary"):
                from comparison import generate_comparison
                results = []
                for criteria, name in sel:
                    d, _ = load_plan_result(criteria, name)
                    if d:
                        results.append((name + ".pdf", d))
                md, csv_path = generate_comparison(results, os.path.join(BASE, "output"), "competition")
                st.session_state["cmp_md"] = md
                st.success(f"已生成：{md}")
            md_path = st.session_state.get("cmp_md")
            if md_path and os.path.exists(md_path):
                with open(md_path, encoding="utf-8") as f:
                    _md_txt = f.read()
                st.download_button("⬇️ 下载对比表（MD）", _md_txt,
                                   file_name="batch_comparison.md", type="primary")
                with st.expander("预览对比表", expanded=True):
                    st.markdown(_md_txt)
        else:
            dims_order, data = [], []
            for criteria, name in sel:
                d, _ = load_plan_result(criteria, name)
                if not d:
                    continue
                label = name[:22]
                for dim in d.get("维度评分", []):
                    dn = dim.get("维度名称", "")
                    if dn and dn not in dims_order:
                        dims_order.append(dn)
                    try:
                        ratio = float(dim.get("得分") or 0) / float(dim.get("满分") or 1) * 100
                    except Exception:
                        ratio = 0.0
                    data.append({"教案": label, "维度": dn, "得分率": round(ratio, 1)})

            if not data:
                st.info("所选教案暂无维度数据")
            else:
                _sv = st.checkbox("在数据点上显示数值", value=(len(sel) <= 3),
                                  help="所选教案较多时建议关闭，否则标签可能重叠")
                chart = build_radar_chart(data, dims_order, show_values=_sv)
                if chart is None:
                    st.info("维度数量不足，无法绘制雷达图")
                else:
                    # 居中显示 + 按图表自身尺寸渲染（width="content"）：
                    #   固定正方形 → 全屏不会被拉伸变形；居中 → 避免右侧大片空白
                    st.markdown(
                        """<style>
                        div[data-testid="stVegaLiteChart"], div[data-testid="stAltairChart"] {
                            display: flex; justify-content: center;
                        }
                        </style>""",
                        unsafe_allow_html=True,
                    )
                    st.altair_chart(chart, width="content")
                    st.caption("雷达图使用 **归一化得分率**（该维度得分 ÷ 满分 × 100），"
                               "因此满分不同的维度（5/10/20 分）可以直接在同一张图上比较；"
                               "越靠外圈表示达成度越高。")


# ============================================================
# 页面 5：设置
# ============================================================

def page_settings():
    st.title("⚙️ 设置")

    st.subheader("① API Key（必填）")
    ks = key_status()
    if ks["configured"]:
        st.success(f"当前已配置：{ks['masked']}　来源：{ks['source']}")
    else:
        st.warning("尚未配置 API Key，评分功能不可用")

    st.caption(
        "把 DeepSeek API Key 粘贴到下面并点「💾 保存」——会写到项目内的 `data/.api_key`，"
        "**下次启动不用再填**（不需要配环境变量）。"
    )
    key_input = st.text_input("DeepSeek API Key", type="password", placeholder="sk-…",
                             key="apikey_input")
    c1, c2, c3 = st.columns([1, 1, 2])
    if c1.button("💾 保存", type="primary"):
        if not key_input.strip():
            st.error("请先填入 Key")
        else:
            from providers import save_local_key
            p = save_local_key(key_input.strip())
            st.success(f"已保存到 {os.path.relpath(p, BASE)}（重启后依然有效）")
            st.rerun()
    if c2.button("🔌 测试连接"):
        test_key = key_input.strip()
        if not test_key and not ks["configured"]:
            st.error("请先填入 Key")
        else:
            with st.spinner("正在测试连接…"):
                try:
                    if test_key:
                        from providers import save_local_key
                        save_local_key(test_key)   # 先落盘，保证 provider 能取到
                    from providers import create_provider
                    prov = create_provider("deepseek", cfg())
                    r = prov.chat("你是助手。", "只回复两个字：正常", temperature=0, max_tokens=16)
                    st.success(f"✅ 连接正常（模型回复：{str(r)[:30]}）")
                except Exception as e:
                    st.error(f"❌ 连接失败：{str(e)[:220]}")
    if c3.button("🗑 清除本地保存的 Key"):
        from providers import save_local_key
        save_local_key("")
        st.warning("已清除本地保存的 Key（若 config.yaml 或环境变量中仍有，会继续生效）")
        st.rerun()

    st.divider()
    st.subheader("② 当前配置（config.yaml）")
    st.json(cfg())

    st.divider()
    st.subheader("复核人姓名")
    st.text_input("复核人", key="reviewer_name", value=st.session_state.get("reviewer_name", ""))

    st.divider()
    st.caption(f"项目目录：{BASE}")


# ============================================================
# 主入口
# ============================================================

def main():
    page = render_sidebar()
    if page.startswith("🏠"):
        page_home()
    elif page.startswith("📝"):
        page_score()
    elif page.startswith("🔍"):
        page_review()
    elif page.startswith("📊"):
        page_batch()
    else:
        page_settings()


if __name__ == "__main__":
    main()
