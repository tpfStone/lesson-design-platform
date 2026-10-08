# P1 实施与验收记录

日期：2026-09-24。范围仅为 `F:\comalesson\Lessongen` 工作树中的 P1 变更；未合并、未推送，也未调用付费模型。P1 的**本地实现已完成，正式 Gate 尚未通过**：还需远端 CI、真实 MySQL 容器测试和负责人对默认审查策略的确认。

## 1. 行为契约（T011–T014）

1. 生成任务默认 `at_least_one_independent_review`。Design Architect → Writer → Judge 形成 v0 后，即使 v0 达到内部门槛，仍进入同轮 Subject、Pedagogy、Alignment 三位 Critic 与 Validator；优化任务也保持初审。显式设置 `judge_first_fast_path` 才允许旧的高分直出对照。
   默认配置的 `experiment_id`/`method_id` 已改为 `_p1_reviewed` 后缀，避免把本轮新策略与历史 v1.6 结果误当成同一方法；旧 run 中已保存的配置不回填。
2. “独立审查完成”由同一轮三位 Critic 完成事件和该轮 ValidationBatch 共同证明。内部分数、单个 Critic 或跨轮凑齐角色都不能证明完成。
3. 无可执行意见：停在 `no_actionable_feedback`，可交付 v0，但不能声称发生内容改写。预算不足：已有 v0 时为 `needs_human/budget_exceeded`。已接受意见但没有改写轮次：`needs_human/max_rounds`。Critic 失败：明确失败并保留已有版本、错误和已知用量。
4. 结果页分别显示仅内部评分、已独立审查但未改写、真实内容变化；非正常停止原因优先于审查摘要。历史结果没有新 `review` 字段时保守展示“尚未证实独立审查”。

离线证据：`paper4_pipeline/tests/fixtures/p1_high_score_v0_review.json` 固定了高分 v0 的状态与事件顺序；`test_graph_integration.py` 覆盖高分、无意见、零改写轮次、预算不足、显式快路、部分 Critic 失败、改写失败与既有优化路线；`test_web_engine.py` 验证跨轮角色不能被错误合并成一次完整审查；前端浏览器测试为快路与已审查未改写状态附带截图。

## 2. 图结构与调用账本（T015–T017）

`Paper4Workflow` 仍是公共入口，LangGraph 节点名与边保持；`graph.py` 保留图装配、运行边界和投影，节点实现分别位于 `design_nodes.py`、`review_nodes.py`、`revision_nodes.py`、`finalization_nodes.py`。本次是在一个工作树中分组迁移并回归，**没有实现原计划中的“每组单独 PR”流程证据**；审核时建议按模块分提交/PR。

真实 Provider 的每次尝试追加到 `model_call_ledger.jsonl`，包含同一调用共用的 call ID、每次尝试独立的 attempt ID、阶段/角色、模型、Prompt/config 指纹、费率指纹、usage 来源、耗时、状态及已知 Token/估算费用；DOCX Normalizer 使用同一记录格式，但其账本位于该任务的 `normalized` 目录，预处理用量仍由 registry 汇总。正常 run 的 `run_result.json` 可携带调用记录，旧 run 无该字段仍能读取。截断重试、402、无 usage、账本写入失败、可捕获的用户取消均有离线用例；写账本失败不会再触发一次付费调用。进程被强制杀死或机器断电仍无法保证最后一条落盘。`null` 表示供应商未给出用量，UI 数字只表示已知部分和。

## 3. 三端契约与界面（T018–T019）

Python `scripts/export_engine_contract.py` 导出带版本号的 `specs/002-project-improvement/contracts/engine-models.json`；`--check` 接入 CI，Java `ContractFixtureTest` 对 Python 必需字段及引擎状态枚举执行兼容检查。Java 将可选 `review` 透传至公开结果，旧数据仍可读。Vue 的 jobs store 在终态结果暂时不可用时继续重试，失败任务可单独展示 recovery；任务页和优化页没有把上传原件当作优化结果。

## 4. 本地验收结果与剩余门槛

| 检查 | 本地结果 |
| --- | --- |
| Python 全量离线测试 | 183 passed；1 条第三方弃用警告 |
| Python 契约导出一致性 | `--check` 通过 |
| Java Maven tests | 27 tests，0 failures/errors，2 skipped（均为 MySQL Testcontainers） |
| Vue Vitest、类型、ESLint、Prettier、OpenAPI、构建 | 全部通过；Vitest 9 tests |
| Edge 浏览器 E2E | 13 tests 通过，含生成、优化、断线、401/402、终态重试与产物列表 404 |

未通过的正式 Gate：本机 `docker info` 无法连接 Docker daemon，故本轮两条 MySQL 容器测试被跳过；GitHub Actions 的新提交检查尚未执行。没有使用真实 DeepSeek 对本次默认初审的耗时、费用和输出质量做付费验收；导师也尚未确认 D04–D06 的研究取舍。离线测试证明路由、契约和展示语义，不证明生成教案质量或教学成效。

## 5. 回滚与上线前确认

- 如默认初审成本不可接受，仅对新运行显式设 `generation_review_policy=judge_first_fast_path`；不能改写已有 run 的配置或把旧快路产物宣传为三方审查。
- 如调用账本出现缺失/损坏，应停止自动付费重试，核对供应商账单与 trace；未知 usage 不可按零费用结算。
- 合并前在有 Docker 的环境运行 CI 的 Java/MySQL 必跑门槛和前端浏览器测试，并由负责人确认 D04–D06。公开部署、真实课堂实验仍属 P3，不由 P1 自动授权。
