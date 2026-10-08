# Lessongen Paper#4：真实多智能体教案闭环

本目录是 Lessongen 的 Paper#4 多智能体教案引擎。所有模型角色均通过 DeepSeek OpenAI-compatible API 调用 `deepseek-v4-flash`；没有离线 Mock 或伪造成功回退。密钥、网络或不可恢复节点错误会明确标记为 `failed`。若只有 Rewriter 在重试后无法满足输出契约、且此前已有通过硬规则的安全版本，系统不会谎称修改成功，也不会抛弃整份教案，而是将意见记为未解决并以 `needs_human` 交付安全版本。

第一次运行请直接阅读 `docs/RUN_GUIDE.md`；为什么新增设计节点、内容字段和黑白灰 Word 版式，见 `docs/QUALITY_UPGRADE_V1_2.md`。v1.3 拆分步骤中的 `resource_ids` 与 `artifact_ids`；v1.4 新增 Alignment Critic；v1.5 修正延期意见回放；当前 v1.6 增加输入证据画像、校准工程质量门、第三轮迭代、改写失败安全降级和离线分析工具。

## 当前闭环

```text
LessonTask
  → Design Architect 生成 2–3 个候选方案并选择教学主线
  → Writer 按选中蓝图生成 v0
  → 硬规则校验
  → Judge 八维内部评价
  → 程序 Router
  → Subject + Pedagogy + Alignment 三类 Critic 独立审查
  → Validator 接受/拒绝/合并/延后
  → 程序 Router
  → Rewriter 只执行已接受意见，生成 v1…vn
  → 修改守恒与硬规则复核
  → Judge 复评 → 停止策略 → 最佳版本选择
  → JSON / Markdown / Word / manifest / JSONL trace
```

模型负责生成和语义判断；程序负责身份、Schema、引用完整性、步骤时长、批评生命周期、预算、路由、版本选择和导出。Judge 的建议不是控制流，内部评分也不能替代教师/专家实验。

项目内 `data/tutorial34_v0_1/` 保存 Tutorial3/4 的开发集与适配测试材料，运行和测试不依赖仓库外的数据文件。

## 角色和异质性

| 角色 | 只允许做的事 | 独立知识包 | 默认参数 |
|---|---|---|---|
| Design Architect | 比较候选认知路径并选择主线 | 任务上下文、参考质量画像 | temperature 0.80 / 6144 tokens |
| Writer | 展开蓝图并生成结构化初稿 | 任务上下文、生成规则、参考质量画像 | 0.60 / 12288 |
| Subject Critic | 学科事实、条件、教材边界 | 任务上下文、教材输入 | 0.15 / 4096 |
| Pedagogy Critic | 认知进阶、支架、参与、调控、差异化、可实施性 | 任务上下文、教学法审查框架 | 0.25 / 4096 |
| Alignment Critic | 课标—目标—活动—产出—评价证据链 | 任务上下文、对齐协议、结构审计 | 0.10 / 4096 |
| Validator | 核验、去重、冲突裁决 | 任务上下文、裁决规则 | 0.00 / 4096 |
| Judge | 冻结八维量表内部评分 | 任务上下文、量表锚点 | 0.00 / 4096 |
| Rewriter | 按接受意见做连贯修订 | 任务上下文、修改守恒规则、参考质量画像 | 0.40 / 12288 |

所有角色固定使用 `deepseek-v4-flash`，但 Profile、可见状态、知识、Prompt、温度和输出 Schema 不同。第一版关闭 thinking mode，使结构化输出和温度实验更可控；配置已保留 `thinking_mode` 与 `reasoning_effort`，后续应作为单独实验变量，不在基线中混用。

## 环境与安装

推荐 Python 3.11 + uv，直接使用 F 仓库的锁文件，不依赖 Conda PR4：

```bat
cd /d F:\comalesson\Lessongen
uv sync --project paper4_pipeline --locked --extra web --extra dev
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup-local.ps1
web\scripts\start-web-engine.cmd --check
```

完整 Web 可只安装 Docker Desktop，再从仓库根运行 `scripts\up.cmd`，无需本机 Python/Java/Node。仓库根 `.env`：

```dotenv
DEEPSEEK_API_KEY=你的真实密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

可从仓库根 `.env.example` 复制变量名。程序只把变量名和“是否存在”写入诊断，不导出密钥值。

## Web Engine

Web 版不调用 CLI 子进程，而是由 FastAPI 适配层直接复用 `PipelineService`。在设置
`ENGINE_INTERNAL_TOKEN`、`PAPER4_WEB_STATE_ROOT`、`PAPER4_ARTIFACTS_ROOT` 和
`PAPER4_CONFIG_PATH` 后启动：

Engine 状态和教案产物默认写入项目内被 Git 忽略的 `var/engine-state` 与
`var/engine-artifacts`；环境变量可覆盖默认值。

```bat
..\web\scripts\start-web-engine.cmd
```

默认只监听 `127.0.0.1:8001`，用一个持久化工作进程串行执行付费任务。除健康检查外，
所有 `/internal/v1` 接口均要求 `X-Engine-Token`；浏览器只能访问 Spring Boot，不能
直接访问这里。上传的 DOCX 先经过 OOXML 安全检查和稳定定位抽取；如果它与系统此前
导出的 Word 完全一致，会校验 manifest 与 JSON 哈希后直接恢复原结构化教案，避免付费
模型重复猜测自己的输出。外部或修改过的 Word 仍由模型结构化，再作为 `initial_plan`
进入 LangGraph。普通超链接、外链图片和外部模板不会被服务访问，只形成导入警告并继续
读取文件内已有的正文与表格；宏、加密包、嵌入 OLE 对象、ZIP 路径穿越和异常压缩包仍
会被拒绝。合并单元格只提取一次，避免固定表格模板把同一段内容重复数倍。
生成和优化的初稿即使内部评分达标，默认也必须先经过同轮三类 Critic 与 Validator 审查；
这会增加模型调用、耗时和费用。只有显式设置
`generation_review_policy=judge_first_fast_path` 的生成实验才可回到高分 v0 快路，
页面会标明该版本没有完成独立审查。审查后无可执行意见不强制制造 v1；预算不足时
保留已有版本供教师复核。系统不会把重复评分当作改写。正常优化产物另含
`optimization_report.json/.md`，明确记录
逐轮意见、裁决和交付稿相对原稿的真实内容差异。分数仅是内部信号，不等于教学效果。

## 命令行

日常使用推荐直接启动交互式生成器：

```bat
.venv\Scripts\python.exe -m paper4_pipeline.cli generate
```

只需填写科目、年级和课题；可选字段可以直接回车，课时、课程说明、教学风格、详细程度等有合理默认值。程序会先保存输入并显示摘要，得到确认后才调用真实模型。配置、输出目录、Word 导出和 `run_id` 均已默认。

运行已有 JSON 文件时也只需提供任务文件：

```bat
.venv\Scripts\python.exe -m paper4_pipeline.cli run --task ".\examples\sample_task.json"
```

先做无费用配置检查：

```bat
.venv\Scripts\python.exe -m paper4_pipeline.cli check
```

自动运行目录名采用 `时间-科目-年级-课题-随机后缀`，既能看懂也不会轻易冲突；交互时可以选填短名称，或用 `--run-name "勾股定理公开课"`。运行结束后，控制台会显示实际 `run_id` 和完整产物目录。

## 输出与可审计性

成功运行目录包含：

- `run_result.json`：任务级结果、所有版本、意见生命周期、用量与费用估计；
- `input_task.json`：交互输入转换后的规范任务，可直接复用或修改；
- `best_lesson_plan.json`：最佳版本规范数据；
- `best_lesson_plan.md`：可阅读教案；
- `best_lesson_plan.docx`：可选 Word 交付；
- `manifest.json`：文件哈希和格式状态；
- `trace.jsonl`：每个 Agent 的输入摘要、知识包、Prompt ID/版本/哈希、模型、响应 ID、结束原因、真实尝试次数、token、费用和耗时。

Provider 使用 DeepSeek JSON Output，并用 Pydantic 再校验；空响应、非法 JSON 或违反领域契约会在限定次数内重试。认证、权限、无效请求和模型不存在属于确定性配置错误，会立即失败，避免重复扣费。

教学步骤中的引用使用两个独立命名空间：`resource_ids` 只能指向 `resources[].resource_id`，`artifact_ids` 只能指向 `teaching_artifacts[].artifact_id`。模型修订失败时，重试会携带上一次无效 JSON 和精确校验错误进行定点修复。若已有通过硬规则的安全版本但 Rewriter 最终仍失败，本轮意见会被如实标为 `unresolved`，运行以 `needs_human/rewrite_failed` 收尾并正常导出最佳安全版本；只有没有可交付安全版本或发生不可恢复节点错误时才标记 `failed` 并导出 recovery 文件。

## 参数与预算

配置文件为 `configs/deepseek_v4_flash.json`。默认最多三轮完整修订，最大 42 次真实尝试、360,000 token、5 美元估算费用和 1,800 秒。Router 按各角色 `max_retries+1` 预留下一段闭环的最坏调用次数，使 `max_model_calls` 不会因结构化重试被突破；token、费用和时间只能在一次服务端调用返回后确认，因此它们是调用间停止边界，可能包含最后一次已发生调用的增量。较高上限用于允许第三轮收敛，不代表每次都会用满；费用单价是可配置快照，最终以服务商账单为准。

默认工程质量门为 `quality_threshold=8.0` 和 `critical_dimension_floor=7.0`。八维始终全部进入等权总分，不按历史最高分动态移动门槛，也不因缺课标而删除维度。Judge 会依据输入证据画像区分“内部教学评一致性”和“外部课标/教材尚未核验”，在不补造来源的前提下评分并披露边界。该分数仍只是内部路由信号，不是论文效果结论；研究实验应冻结任务集、人工量表和参数，并报告人的评价。

历史结果可用 `python -m paper4_pipeline.cli analyze` 做零 API 调用的评分与状态统计；单次运行可用 `python -m paper4_pipeline.cli export-process --run-dir ".\artifacts\<run_id>"` 导出完整过程报告。

## Prompt 设计

八份版本化 Prompt 采用“先设计、再成稿”：Design Architect 先比较 2–3 条不同认知路径，Writer 展开选中方案并提供真实材料、学生产出和成功标准；三个 Critic 分别审查学科正确性、学习过程和教学评一致性，Validator 每轮聚焦最多 5 条高杠杆意见，Rewriter 允许在已接受意见范围内做连贯重构。方法依据和版本说明见 `prompts/DESIGN_NOTES.md`。

## Paper#3 与人的实验边界

`adapters/paper3.py` 已定义 `SimulationReport → CritiqueBatch` 的适配合同，但配置默认不把课堂模拟接入主图；接入前须冻结 Paper#3 输出版本、证据 ID 和时间语义。真实师范生与中小学教师试用属于下一阶段：保存知情同意后的操作数据、版本选择、修改行为、专家评分和反馈；不能用内部 Judge 分数代替。

## 测试

```bat
cd /d F:\comalesson\Lessongen\paper4_pipeline
.venv\Scripts\python.exe -m pytest -q
```

离线测试只检查领域合同、路由、生命周期、配置、Prompt 哈希、异质知识和导出，不伪装成模型效果。正式验收必须额外完成一次真实 API 运行并检查 trace 中八类角色的模型元数据。
