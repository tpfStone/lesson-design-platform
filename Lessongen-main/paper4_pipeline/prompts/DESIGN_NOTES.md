# Prompt 设计依据与工程映射

这些 Prompt 不是把论文文字复制进系统，而是把可复现的方法原则转成角色边界、输入字段、输出 Schema 和程序校验。论文证据用于提出设计假设，不代表当前实现已经获得相同实验效果。

## 参考工作

- Fan 等（UIST 2024），*LessonPlanner: Assisting Novice Teachers to Prepare Pedagogy-Driven Lesson Plans with Large Language Models*：采用课程信息/目标锚定、按当前教学部分选择相关教学事件、链式保留上下文、简单格式与示例以提高稳定性，并强调教师可见和可调。映射到 Writer 的任务锚定、必要教学事件、可追踪结构和 Web 层未来的人类控制。
- Hu 等（IEEE TLT 2024），*Teaching Plan Generation and Evaluation With GPT-4*：使用 PCK 基础的统一教学设计框架、数学问题链、分阶段提示、明确输出格式和示例。映射到 Writer 的内容知识/教学法/学情整合、认知问题链和 JSON 示例。
- Zheng 等（2025），*Knowledge-enhanced large language models for automatic lesson plan generation*（LessonPlanLM）：用知识库增强、结构化分步生成和人工定义维度的自我批评提高完整性与一致性，同时其结果提醒自动评分与人工判断并不等价。映射到角色异质知识包、Critic/Judge 分离、冻结量表，以及“内部 Judge 不是正式实验结论”的限制。
- Li 等（AAAI 2025 iRAISE Workshop），*ARCHED: A Human-Centered Framework for Transparent, Responsible, and Collaborative AI-Assisted Instructional Design*：强调分阶段工作流、目标与评价对齐、透明报告和教师主导。映射到可审计 trace、Validator、修改映射、可导出交付物和 Human Reviewer 的后续接口。

## 为什么分成八类调用

同一个底座模型并不等于同一个 Agent。实验变量通过 Profile、可见状态、知识包、Prompt、温度与输出契约隔离：Design Architect 生成并选择候选设计；Writer 只负责展开；Subject Critic 仅查学科；Pedagogy Critic 仅查学习过程；Alignment Critic 审查课标—目标—活动—产出—评价证据链；Validator 处理依据、重复、依赖与冲突；Judge 按冻结量表诊断但无路由权；Rewriter 只能执行接受意见。Router、版本选择、硬规则和预算是程序逻辑，不能由模型自行决定。

## 当前可研究变量

第一版固定模型为 `deepseek-v4-flash`，先验证闭环与数据记录。后续在不改变任务集和量表的前提下，可比较：同质/异质知识、单/双/三 Critic、独立审查/辩论、单轮/多轮、是否接入 Paper#3 模拟证据。人的实验与专家评分应单独设计，不能用内部 Judge 分数代替。

## v1.4：三类 Critic 的正交分工

将原 Pedagogy Critic 同时承担的“学习过程质量”和“教学评一致性”拆开：Subject 负责事实与教材边界；Pedagogy 负责认知进阶、支架、参与、差异化、反馈调控和可实施性；Alignment 负责课程依据—目标—活动—学生产出—评价证据—成功标准的可追溯与语义一致。三个角色读取同一版本但不读取彼此本轮输出，随后由 Validator 横向去重、识别依赖和裁决冲突。Alignment 还接收程序生成的结构审计；该审计只暴露缺失链接，语义是否真正对齐仍由模型判断。

## v1.1：从“守规矩”转向“有边界的创造”

v1.0 真实运行结构稳定，但容易收敛到通用五段式；双 Critic 共提出 13 条意见且全部被接受，使 Rewriter 更像逐条修补。v1.1 保留事实、身份、课时、Schema 和追踪等硬边界，同时把教学结构视为开放设计空间：Writer 内部比较多条教学主线，围绕认知冲突、递进问题链、学生作品和教师追问形成有辨识度的课堂；Critic 先识别值得保护的创意；Validator 每轮最多接受 5 条高杠杆意见；Rewriter 可以为连贯落实意见同步调整相关字段，并明确保护原有教学灵魂。该调整是假设，仍需与 v1.0 在同一任务和人工量表上对照。

> 注意："每轮最多 5 条"不再只是 Prompt 请求。它是结构约束：`control/lifecycle.py::enforce_acceptance_cap` 在 Validator 记录/应用裁决前按 priority 保留下游 merge 锚点，超额 ACCEPT 转 DEFER。编辑此规则时请同步维护 Prompt 措辞、该函数与 `DEFAULT_MAX_ACCEPTS_PER_ROUND`。

## v1.2：先设计再成稿，并把“内容可用性”写进合同

用户提供的英语教案样例显示了连续表格、清晰前置分析和三类课堂信息并列的优点，也暴露了笼统活动、评价栏过窄、品牌广告和空白反思页等问题。v1.2 没有复制样例文本，而是形成版本化参考画像 `data/reference_profiles/lesson_design_quality_v1_2.md`。

架构新增 Design Architect：先输出 2–3 个在认知路径上真正不同的候选方案，再选择一条交给 Writer，避免 Writer 一次调用同时承担发散、选择和长篇成稿。LessonPlanDocument 以向后兼容方式增加设计主张、驱动问题、学习轨迹、可直接使用的教学材料、学生产出、成功标准、支架、拓展、追问和教师调控分支。Judge 的 v1.2 评分锚点明确规定，只有结构而缺少真实材料的教案不能得到高分；未知语义修改也不再被程序自动标为 VERIFIED_FIXED，而要等待下一轮独立审查证据。

Word 导出改为 A4 黑白灰打印版：连续三列表格对应“教师活动—学生任务与产出—评价与调控”，评价列保留可读宽度，去除蓝色品牌样式，并将材料正文和成功标准导出。该版式是参考启发下的重新设计，不复制学校标识、学科网广告或具体课文。

## v1.5：控制层的三个结构收口

真实运行数据（约 99 条 critique）暴露了几处“模型正确但控制层放水/空转”的问题，本次用确定性结构修正，不新增模型调用：

1. **接受上限顺延必须重新核验。** `enforce_acceptance_cap` 会把超出每轮上限的 ACCEPT 结构性转为带 cap 标记的 DEFER。v1.4 曾在 Rewriter 前将这类意见直接 `DEFERRED→REOPENED→ACCEPTED`，既绕过了当前版本的 Validator，又可能和本轮同 ID 意见重复，甚至突破 5 条接受上限。v1.5 改为在下一轮 Critic 之后、Validator 之前调用 `control/lifecycle.py::reopen_cap_deferred_for_validation`：只把更早轮次、从未复启、且未与本轮 ID 冲突的意见转成 REOPENED；随后与本轮新意见组成同一个批次，针对当前教案重新接受/拒绝/合并/延后，并共同受每轮 5 条上限约束。每轮至多复启 3 条，每条一生至多一次；Validator 主动 DEFER 且没有 cap 标记的意见不自动复启。
2. **Verifier 的缺失探针只降级、从不认证。** 真实运行中四条遗留确定性 code 从未命中，非确定性 IMPLEMENTED 永远不升级。现增加 `_presence_resolution` 探针：仅当 critique 文本（issue/evidence/code/location）出现“为空/缺少/未提供/missing/absent”等缺失措辞、且 target_path 直接指向某个文档顶层内容字段（`_PRESENCE_FIELDS`）时，若该字段仍为空则把声称 IMPLEMENTED 的意见确定性降为 UNRESOLVED——改写映射声称已修复而字段仍空，属于谎报。内容在场不等于意见被满足，因此探针永不产生 VERIFIED_FIXED（认证仍是确定性 code 专属），也永不惩罚嵌套元素质量类意见。
3. **改写失败降级为可恢复终止。** 若 Rewriter 重试后仍无法产出满足契约（含引用完整性）的新版本，不再让整轮只留下笼统 `RUNTIME_ERROR`：图以 `_abort_rewrite` 记录失败，将本轮 ACCEPTED 全部确定性转 UNRESOLVED，以 `FAIL` 决策 + `StopReason.REWRITE_FAILED` 停靠。FAILED 但已有完整版本时仅导出 `recovery_lesson_plan.json/.md`，JSON 明示 `run_status=failed` 与 `recovery_only=true`，Markdown 显示失败警告；无 manifest/docx，也绝不使用 `best_lesson_plan.*` 名称冒充完成。

Rewriter v1.5 同时取消了 v1.4 的“若当前稿已满足仍建立 implemented change”规则。进入 Rewriter 的意见刚刚由当前版本 Validator 接受，正常情况下必须产生真实、可定位的修改；若仍发现意见已经过时、已满足或互相矛盾，应如实列入 unresolved，而不是伪造 before/after 记录。

“真实修改”也不只靠 Prompt：LiveRewriter 会用 critique 的 JSON Pointer/领域 ID 路径同时解析改写前后文档，`changes` 中每一项的目标值必须可观察地改变；目标在两侧都无法解析、目标值未变化、重复 ID、把 unresolved 塞进 changes，都会触发结构化重试。若所有意见都无法落实，允许保持原文并全部写入 `unresolved_critique_ids`，但不得在无 change 映射时暗改正文。

三个 Critic 当前在一个图节点内依次独立调用。若后一个 Critic 失败，节点级异常会携带前面已成功调用与本次失败尝试的累计 attempts、token 和费用；trace 同时记录已完成 Critic 与 `critic_failed` 事件。这样一次节点没有提交状态，也不会导致已发生的 API 消耗从 `run_result.json` 中消失。

模型调用预算按真实 attempt 计数。Router 不再假设下一角色都能一次成功，而是按每个待调用 Profile 的 `max_retries+1` 预留完整下一段闭环；生成模式启动前也要求预算至少覆盖 Design Architect、Writer、首轮 Judge 的最坏尝试数。因而 `max_model_calls` 是硬边界。token、费用和运行时间只有一次远端调用返回后才能准确知道，仍属于调用间停止边界，最后一次已发生调用的消耗会如实计入而不能撤销。

轮次触顶与预算停靠分开判断：当当前版本已经满足 `iteration >= max_rounds` 时，下一轮根本不会启动，因此不再用下一轮的最坏重试预留触发 `BUDGET_EXCEEDED`，主停靠标签为 `MAX_ROUNDS`。若调用次数、token、费用或时间本身已经真实达到上限，预算原因仍会保留，并继续按安全优先级作为主因。

> 注意：`RouteAction.ROLLBACK`（回归护栏）在 v0.1 图中没有真正的回滚节点，因此把 ROLLBACK 停靠映射为 `FAILED`（回归属安全失败，绝不记为假完成），best 版本仍可降级导出供人审。REGRESSION 目前仅来自确定性 VERIFIED_FIXED 被再次探测失败，判给 Judge 而不虚构回滚。
