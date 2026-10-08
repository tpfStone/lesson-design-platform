# Paper#4 实现状态（2026-09-10）

## 已完成

- 将原项目的 `.env`/`DEEPSEEK_API_KEY`/`DEEPSEEK_BASE_URL` 读取方式迁移为单一 Provider 边界；密钥不进入状态和产物。
- 八类模型角色全部调用 `deepseek-v4-flash`，并有独立 Profile、知识包、Prompt 和参数。
- 使用 DeepSeek JSON Output + Pydantic Schema 双重结构约束；解析或领域规则不通过会进行有上限的真实重试。
- LangGraph 闭环覆盖 Design Architect、Writer、Judge、三 Critic、Validator、Rewriter、复核、复评、程序化停止和最佳版本选择。
- Trace 记录 Prompt 哈希、模型响应元数据、真实尝试次数、token、费用估计、知识包和每轮版本变化。
- 交付层支持规范 JSON、Markdown、默认 Word、manifest 和命令行；交互入口只要求科目、年级、课题，其余可回车跳过。
- 配置、输出目录和 Word 导出已有默认值；`run_id` 自动使用本地时间、任务信息和防冲突后缀生成，交互输入另存为 `input_task.json`。
- Paper#3 的输入边界保留为结构化适配器，不在证据协议未冻结前假装已联动。
- 90 项离线测试覆盖路由、预算、生命周期、三 Critic 职责隔离、对齐审计、输入证据画像、知识隔离、Prompt、设计蓝图、Word 版式、导出、离线历史分析、过程报告、命令默认值、自动命名，以及完整 stubbed LangGraph 的延期回放、改写降级、Critic 中途失败记账和重试预算预留链路。路由测试额外区分“实际预算已触达”和“下一轮最坏重试预留不足”：达到 `max_rounds` 时，不会再把根本不会发生的下一轮预留标成预算耗尽。

## Prompt 不是普通角色扮演

当前 v1.6 方法把论文启发和用户样例的可迁移质量信号落实为可测试约束：先比较候选设计再成稿；课程/学生/目标锚定；真实任务材料、问题链、学生作品、成功标准与教师调控；角色异质知识；Validator 聚焦高杠杆意见并重新核验跨轮延期项；Rewriter 维持 critique ID 守恒且不得用无实际修改的记录冒充落实；Judge 依据输入证据画像区分内部一致性与外部资料核验边界；不输出隐藏思维链。完整说明见 `prompts/DESIGN_NOTES.md`。

## 部署决策

基线关闭 thinking mode。原因是当前首要风险是长 JSON 的稳定解析、可复现参数和费用，不是最大化开放式推理；DeepSeek 文档说明 thinking 开启后 temperature/top_p 不生效。等基线任务通过人工评价后，可将 thinking 模式作为独立变量，只对 Subject Critic、Validator 或 Judge 做对照，不应同时更换 Prompt 与量表。

参数按角色区分：Writer 保留适度多样性；Critic 低温；Validator/Judge 零温；Rewriter 低温且给更大的输出预算。所有角色模型名由 ExperimentConfig 校验，任何角色不是 `deepseek-v4-flash` 都拒绝启动。

## 真实运行状态

有效密钥已经完成过多次旧版真实闭环并记录实际 token 与费用估计，证明 Provider、Agent、LangGraph、Trace 和交付链路是真实执行而非 Mock。当前八角色、三 Critic、v1.6 证据画像、延期回放、改写安全降级和新版 Word 导出已通过离线合同和 stubbed 图级集成测试，但仍需用同一任务执行一次 v1.6 真实 API 闭环并做人工对照；旧结果不能替代当前版本的质量结论。

## 下一轮质量验收

1. trace 中出现 Writer、三类 Critic、Validator、Rewriter 和两次 Judge 的成功响应元数据；
2. 至少保存 v0 与 v1，所有 accepted critique 均有修改或 unresolved 映射；
3. 输出 JSON/Markdown/Word，manifest 哈希全部有效；
4. Word 渲染后逐页检查表格、分页、中文字体和内容完整性；
5. 报告真实 token、估算费用、停止原因和最佳版本，不把内部评分写成实验成效。
