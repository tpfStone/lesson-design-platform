r"""
生成可交付的发布包（白名单复制，不动原目录）

产物：
  E:\BiaoZhu-release\System-v1.2\      ← 交付目录（可直接拷给同学/老师）
  E:\BiaoZhu-release\System-v1.2.zip   ← 压缩包（便于发送）

v1.2 相对 v1.1 的改动（2026-10-04）：
  - 修复：科目识别误判（改为加权计分制）
  - 修复：扫描版 PDF 报技术性错误（三层友好提示 + 引导安装 OCR）
  - 调整：评分标准固定「学生标准」、提示词固定「v2」，界面不再提供选项
  - 调整：批注等级由五档改为 A/B/C（按学生标准分值区间换算）
  - 新增：一级维度分组（产物 + Web 界面）；一级维度不评等级
  - 新增：批量上传、对比表勾选、维度雷达图（归一化得分率）
  - 新增：复核结果一键下载
  - 文档：新增 docs/OCR安装与使用说明.md + tools/install_ocr.bat

用法: python tools/pack_release.py
"""
import os
import shutil
import zipfile
from datetime import datetime

SRC = r"E:\BiaoZhu"
REL_ROOT = r"E:\BiaoZhu-release"
VER = "System-v1.2"
DST = os.path.join(REL_ROOT, VER)

# ---- 白名单：核心代码 ----
CORE_PY = [
    "pipeline.py", "service.py", "parsers.py", "providers.py", "prompts.py",
    "anchors.py", "suggester.py", "annotator.py", "docx_annotator.py",
    "pdf_annotator.py", "comparison.py", "knowledge_base.py", "standards.py",
]
ROOT_FILES = ["README.md", "config.yaml", "requirements.txt", "start_web.bat"]

# ---- docs 精选（排除内部/过程文档）----
DOCS = [
    "部署与使用说明.md",
    "教案智能批注系统-设计说明.md",
    "教案智能批注系统-功能说明.md",
    "知识库构建与标准切换-实现详解.md",
    "交付规划与文件清单.md",
    "粗评交接说明-给同学.md",
    "OCR安装与使用说明.md",
    "变更记录-System-v1.1.md",
    "变更记录-System-v1.2.md",
    "待办10项实施方案.md",
]

# ---- knowledge_base 排除项（构建中间产物/备份）----
KB_EXCLUDE_SUFFIX = ("_kebiao_raw.json",)
KB_EXCLUDE_CONTAINS = ("_backup_",)

# ---- data 下的样例教案（数学/英语各一份，体积小）----
PLAN_SAMPLES = [
    "数学《第六单元_小数的加法和减法》教案教学设计.docx",
    "六年级 下册 PEP英语《Unit2 Last weekend》.docx",
]

# ---- samples/：从产物里挑样例 ----
# v1.2：改用「学生标准」的新格式产物（含 A/B/C 等级 + 一级维度分组）
SAMPLE_CRITERIA_DIR = "student"
SAMPLE_ARTIFACTS = [
    ("数学《第六单元_小数的加法和减法》教案教学设计",
     ["_批注报告.docx", "_已批注.docx", "_评分清单.json", "_评分清单.md"]),
]


def ensure(d):
    os.makedirs(d, exist_ok=True)


def main():
    if os.path.exists(DST):
        shutil.rmtree(DST)
    ensure(DST)

    log = []

    # 1) 核心代码
    for f in CORE_PY + ROOT_FILES:
        src = os.path.join(SRC, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(DST, f))
        else:
            log.append(f"⚠ 缺失：{f}")
    log.append(f"✓ 核心代码 {len(CORE_PY)} 个模块 + {len(ROOT_FILES)} 个根文件")

    # 2) web/
    ensure(os.path.join(DST, "web"))
    shutil.copy2(os.path.join(SRC, "web", "app.py"), os.path.join(DST, "web", "app.py"))
    log.append("✓ web/app.py")

    # 3) tools/（全部，已做路径改造）
    shutil.copytree(os.path.join(SRC, "tools"), os.path.join(DST, "tools"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    n_tools = len([f for f in os.listdir(os.path.join(DST, "tools")) if f.endswith(".py")])
    log.append(f"✓ tools/（{n_tools} 个脚本）")

    # 4) docs/（精选）
    ensure(os.path.join(DST, "docs"))
    for f in DOCS:
        src = os.path.join(SRC, "docs", f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(DST, "docs", f))
    log.append(f"✓ docs/（精选 {len(os.listdir(os.path.join(DST,'docs')))} 个）")

    # 5) knowledge_base/（排除中间产物与备份）
    #    v1.1：同时拷贝 .docx（设计理论源文档，修复"理论库缺失"）
    ensure(os.path.join(DST, "knowledge_base"))
    kb_n = 0
    for f in os.listdir(os.path.join(SRC, "knowledge_base")):
        if f.endswith(KB_EXCLUDE_SUFFIX) or any(k in f for k in KB_EXCLUDE_CONTAINS):
            continue
        if f.endswith((".json", ".docx")):
            shutil.copy2(os.path.join(SRC, "knowledge_base", f),
                         os.path.join(DST, "knowledge_base", f))
            kb_n += 1
    log.append(f"✓ knowledge_base/（{kb_n} 个数据文件，已排除 OCR 原始文本与备份）")

    # 6) output/anchors/（锚点库 —— 核心资产）
    ensure(os.path.join(DST, "output", "anchors"))
    for f in ["anchor_math.json", "anchor_english.json"]:
        src = os.path.join(SRC, "output", "anchors", f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(DST, "output", "anchors", f))
    log.append("✓ output/anchors/（数学/英语锚点库）")

    # 7) data/（示例 + 标准 + 样例教案）
    ensure(os.path.join(DST, "data", "examples"))
    ex_src = os.path.join(SRC, "data", "examples", "示例1")
    if os.path.isdir(ex_src):
        shutil.copytree(ex_src, os.path.join(DST, "data", "examples", "示例1"))
    ensure(os.path.join(DST, "data", "criteria"))
    for f in os.listdir(os.path.join(SRC, "data", "criteria")):
        shutil.copy2(os.path.join(SRC, "data", "criteria", f),
                     os.path.join(DST, "data", "criteria", f))
    ensure(os.path.join(DST, "data", "plans"))
    ps = 0
    for f in PLAN_SAMPLES:
        src = os.path.join(SRC, "data", "plans", f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(DST, "data", "plans", f))
            ps += 1
    # 数据目录说明
    with open(os.path.join(DST, "data", "README.md"), "w", encoding="utf-8") as fh:
        fh.write("# data 目录说明\n\n"
                 "- `examples/` 标注示例（评分时作为 Few-Shot 参考，必需）\n"
                 "- `criteria/` 评分标准（竞赛 4 学科 + 学生标准）\n"
                 "- `plans/` **待评教案放这里**（现含 2 份样例，可自行增删）\n")
    log.append(f"✓ data/（示例 1 份 + 标准 {len(os.listdir(os.path.join(DST,'data','criteria')))} 个 + 样例教案 {ps} 份）")

    # 8) samples/（产物样例，让用户先看效果）
    ensure(os.path.join(DST, "samples"))
    sn = 0
    for base, suffixes in SAMPLE_ARTIFACTS:
        d = os.path.join(SRC, "output", SAMPLE_CRITERIA_DIR, base)
        for sfx in suffixes:
            src = os.path.join(d, f"{base}{sfx}")
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(DST, "samples", f"{base}{sfx}"))
                sn += 1
    if sn:
        with open(os.path.join(DST, "samples", "说明.md"), "w", encoding="utf-8") as fh:
            fh.write("# 产物样例\n\n"
                     "这是同一份教案（《小数的加法和减法》，**学生标准**）评分后生成的全部产物，可先看效果：\n\n"
                     "- `*_批注报告.docx` —— **按一级维度分章节** + 二级维度等级（A/B/C）+ 评分汇总（推荐先看这个）\n"
                     "- `*_已批注.docx` —— 在原始教案上加的 Word 原生批注（用 Word 打开看右侧批注栏）\n"
                     "- `*_评分清单.json` / `.md` —— 结构化数据（含 `一级维度汇总` 字段，便于统计/二次分析）\n\n"
                     "> 说明：批注等级 A/B/C 按学生标准的分值区间由维度得分换算；"
                     "一级维度只做归组展示、不评等级。\n")
    log.append(f"✓ samples/（{sn} 个产物样例）")

    # 9) 打包 zip
    zip_path = os.path.join(REL_ROOT, f"{VER}.zip")
    if os.path.exists(zip_path):
        os.remove(zip_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for r, ds, fs in os.walk(DST):
            ds[:] = [d for d in ds if d != "__pycache__"]
            for f in fs:
                fp = os.path.join(r, f)
                z.write(fp, os.path.relpath(fp, REL_ROOT))
    zsize = os.path.getsize(zip_path) / 1024 / 1024
    log.append(f"✓ 打包 {os.path.basename(zip_path)}（{zsize:.2f} MB）")

    print("\n".join(log))
    print(f"\n交付目录：{DST}")
    print(f"压缩包：{zip_path}")


if __name__ == "__main__":
    main()
