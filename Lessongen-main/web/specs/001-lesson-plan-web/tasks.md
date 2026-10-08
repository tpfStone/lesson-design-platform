# 开发任务清单

## 使用规则

- 任务按编号与依赖执行；标记 `[P]` 的任务可与同阶段其他 `[P]` 项并行。
- 每个垂直切片先写契约/失败测试，再写最小实现，再回归。
- 测试中的固定响应或 stub 只用于隔离外部 API；生产代码禁止 Mock Agent、硬编码教案或假进度。
- 每阶段退出条件未满足，不进入依赖它的下一阶段。
- 本清单中的路径均相对 `Lesoongen/`；Python 路径相对现有 `paper4_pipeline/`。

## Phase 0：基线与契约冻结

- [x] T001 记录 Java、Maven、Node、npm、Python、MySQL 版本，在 `docs/development-environment.md` 写可复现实测版本。
- [x] T002 修正 `pom.xml` 的测试依赖并跑通当前 Spring Boot 空项目测试；不在本任务升级大版本。
- [x] T003 将 `contracts/openapi.yaml` 加入 OpenAPI lint；生成请求/响应 fixture，冻结 `JobStatus`、错误码和字段命名。
- [x] T004 在 Python 中写内部 API 的 Pydantic request/response schema 契约测试，但尚不启动真实模型。
- [x] T005 建立 `.env.example`，只写变量名与假值；确认 `.gitignore` 排除 `.env`、storage、artifacts、日志和上传文件。

退出条件：两个项目基线测试通过，公开 API 与内部 API 的 fixture 可被双方解析，仓库扫描不到真实 Key。

## Phase 1：Java 任务骨架与 MySQL

- [x] T006 增加 validation、JPA、Flyway、Actuator、MySQL Testcontainers 依赖。
- [x] T007 [P] 在 `src/main/java/com/zone/lesoongen/domain/job/` 实现 `LessonJob`、状态枚举与显式迁移方法；先覆盖合法/非法/终态迁移单测。
- [x] T008 [P] 在 `src/main/java/com/zone/lesoongen/domain/artifact/` 实现 Artifact 值对象和归属约束。
- [x] T009 按 `data-model.md` 编写 `src/main/resources/db/migration/V1..V3`，使用 Testcontainers 验证全新库迁移及约束。
- [x] T010 实现 Repository port 与 JPA adapter；分页查询不读取大型 JSON 或文件。
- [x] T011 实现 `StoragePort` 和 `LocalStorageAdapter`：临时文件、原子提交、SHA-256、相对键和根目录逃逸测试。
- [x] T012 实现 RFC 9457/Problem Details 风格异常映射、稳定错误码与 correlation id 脱敏日志。

退出条件：数据库从空库启动；并发抢占测试证明一个 QUEUED 任务只能被一个 dispatcher 获得；任意 `../` 存储键被拒绝。

## Phase 2：Python generate 垂直切片

- [x] T013 在 `src/paper4_pipeline/web_api/` 增加 FastAPI app、配置、健康检查和内部 token 验证。
- [x] T014 实现持久化 `EngineRunRegistry`，以 `external_job_id` 幂等创建 run；重启后能从 artifacts/trace 判断未知、运行中和终态。
- [x] T015 实现单工作器队列或专用 worker 进程，正式调用现有 `PipelineService.run`；不得复制 graph 或调用 CLI 子进程。
- [x] T016 将现有 trace 中的节点事件投影为公开阶段事件，过滤 Prompt、思维链、原文全文、密钥和绝对路径。
- [x] T017 实现 generate 创建、状态、事件、结果、artifact 下载端点及 schema/幂等/恢复测试。
- [x] T018 运行 Paper#4 现有全部回归，确认 Web wrapper 没有改变 Agent、路由和导出语义。

退出条件：用测试 agent suite 完成一次内部 API 生成闭环；进程重启后可查询原 run；正式包中不存在返回固定教案的分支。

## Phase 3：Spring generate 编排与公开 API

- [x] T019 按 OpenAPI 创建公开 DTO、Controller 和校验；Java 只保留 Web 字段，EngineClient 负责 snake_case 映射。
- [x] T020 实现 `CreateGenerateJobUseCase`：规范化请求、请求哈希、24 小时幂等、QUEUED 入库和 202 响应。
- [x] T021 实现 `EngineClient`，用 WireMock 覆盖成功、同 id 重试、超时、402、429、5xx 与异常响应。
- [x] T022 实现数据库驱动的 `DispatchQueuedJobsUseCase`，配置 `max-concurrent-jobs=1`。
- [x] T023 实现 `ReconcileRunningJobsUseCase`：拉取快照/事件、严格状态迁移、事件去重、终态和用量落库。
- [x] T024 实现 job 列表/详情/result/artifact API；下载前校验 job 归属、存储根、长度与哈希。
- [x] T025 实现 SSE snapshot、Last-Event-ID 补发、心跳、断开清理及轮询回退所需详情字段。

退出条件：Spring 集成测试从 POST 202 一直推进到 COMPLETED；刷新/重启后任务仍可恢复；重复提交不产生第二个 Engine run。

## Phase 4：Vue generate 垂直切片

- [x] T026 使用 Vue 3 + TypeScript + Vite 初始化 `frontend/`，加入 Router、Pinia、Element Plus、Vitest、MSW、Playwright 和 lint/format。
- [x] T027 [P] 建设计令牌、响应式 shell、导航、字体层级、焦点态、空态和 reduced-motion 基线。
- [x] T028 [P] 根据 OpenAPI 建类型化 API client、Problem Details 适配器与幂等键生命周期。
- [x] T029 实现“生成教案”分组表单：三项必填、默认课时、可增删数组、草稿恢复、提交锁和字段错误定位。
- [x] T030 实现任务过程页：真实阶段时间线、轮次、SSE 连接状态、2 秒轮询退化和刷新恢复。
- [x] T031 实现结果页：结构化教案预览、八维雷达/列表、内部评价提示、最佳/最后版本、产物下载。
- [x] T032 实现近期任务页与 mode/status 筛选。
- [x] T033 以 MSW/固定契约完成生成、断网重连、失败、needs-human、下载 E2E。

退出条件：不懂 JSON 的用户可完成生成；键盘可走通核心路径；页面不显示假阶段、Prompt 或绝对路径。

## Phase 5：DOCX 优化能力

- [x] T034 [P] 建安全 DOCX fixture 集：正常段落、复杂表格、伪扩展名、损坏 ZIP、宏、外链、Zip Slip、高压缩比和超限文件。
- [x] T035 在 Python 实现 `SafeDocxInspector`，限制入口数量、单项大小、总展开大小与压缩比，拒绝宏/OLE/外部关系/加密包。
- [x] T036 实现 `DocxExtractor`，为段落、标题、列表、表格单元格产生稳定 source locator 和 warning。
- [x] T037 实现 `DocxNormalizer` Prompt、结构输出、两次修复、Pydantic 校验、元数据来源和必须保留映射；测试使用保存的模型结构响应。
- [x] T038 实现 optimize 内部端点，将规范化结果作为 `LessonTask(mode=optimize, initial_plan=...)` 调用同一个正式 graph。
- [x] T039 Spring 实现流式上传：先到隔离临时区，校验通过再提交；登记原文件、哈希、解析状态和规范化 artifact。
- [x] T040 实现公开 optimize multipart Controller 和 EngineClient；覆盖超限、非法 DOCX、规范化失败、模型失败与 recovery。
- [x] T041 Vue 实现拖放上传、上传状态、排版不保真说明、优化重点/必须保留输入、警告与摘要级前后变化。
- [x] T042 用 5 份结构不同的真实脱敏 DOCX 进行解析与视觉验收，至少 4 份可靠进入优化；失败样例必须明确失败而非生成空壳。

退出条件：原文件不被覆盖；用户元数据优先；优化真正从原稿结构化结果进入现有 pipeline；结果 Word 可下载且 SHA-256 匹配。

## Phase 6：稳定性、安全和视觉完成度

- [x] T043 [P] 完成上传/下载安全、CORS、反向代理大小、日志脱敏、依赖漏洞和 secret scan。
- [x] T044 [P] 完成窄屏、平板、桌面、键盘、对比度、焦点、屏幕阅读器标签和 reduced-motion 检查。
- [x] T045 [P] 完成骨架屏、阶段切换、卡片进入、结果展开和图表过渡；仅对 transform/opacity 做主要动画。
- [x] T046 实现启动对账：Spring 重启后恢复非终态；Python 不可达时保持可解释状态，不误标 FAILED/COMPLETED。
- [x] T047 实现 artifact 原子复制、哈希不匹配拒绝、缺失文件降级和 recovery 下载。
- [x] T048 完成所有 Java/Python/Vue 自动测试、OpenAPI lint 和生产构建。
- [x] T049 受控真实生成 1 次、真实优化 1 次，记录模型/Prompt/config 版本、调用量、费用、运行时间和人工检查。
- [x] T050 按 `ui-spec.md` 做浏览器截图走查，并修复所有 P0/P1 视觉与交互问题。

退出条件：核心 E2E 全绿；无真实密钥和用户教案进入仓库；两次真实验收形成完整 Word；失败时网页给出准确可执行建议。

## 明确延后

- 登录、组织与 RBAC；
- 课程标准/教材附件与 RAG；
- Paper#3 模拟证据接入；
- 浏览器 Word 富文本编辑与原样式保真；
- Redis/Celery、多机并发、MinIO/OSS；
- 人的实验与研究统计模块。
