# 实施计划：教案生成与优化 Web MVP

## 1. 架构结论

采用三层服务，而不是把 Python 脚本塞进 Spring Boot 进程：

```text
Vue 3 SPA
  │ HTTPS / JSON / multipart / SSE
  ▼
Spring Boot（公开 API 与业务主控）
  ├─ MySQL：任务、状态、事件、产物元数据
  ├─ StoragePort：本地文件存储（以后可替换 MinIO/OSS）
  └─ EngineClient：仅访问 Python 内部 API
          │ 内网 HTTP / JSON
          ▼
Python FastAPI Engine
  ├─ DOCX 安全检查、抽取与规范化
  ├─ 现有 paper4_pipeline / LangGraph
  └─ JSON / Markdown / Word / trace 导出
```

职责原则：Vue 不编排业务；Java 不复制 Pydantic/LangGraph 逻辑；Python 不管理 Web 用户和公开下载权限；MySQL 不充当 DOCX/trace 文件系统。

## 2. 代码布局

保持当前 Spring Boot 工程根目录不搬迁：

```text
Lesoongen/
├─ pom.xml
├─ src/main/java/com/zone/lesoongen/
│  ├─ api/                 # Controller、公开 DTO、异常映射
│  ├─ application/         # 用例、任务服务、协调器、状态迁移
│  ├─ domain/              # Job/Artifact/Event 领域对象与枚举
│  ├─ infrastructure/
│  │  ├─ persistence/      # JPA Repository 与 Entity
│  │  ├─ engine/           # Python EngineClient
│  │  ├─ storage/          # LocalStorageAdapter
│  │  └─ scheduling/       # 队列派发和状态对账
│  └─ config/
├─ src/main/resources/
│  ├─ application.yml
│  └─ db/migration/        # Flyway
├─ frontend/               # Vue 3 + TypeScript + Vite
└─ specs/001-lesson-plan-web/
```

Python 不复制到 Java 工程。现有 `paper4_pipeline` 增加独立的 `web_api` 包和启动入口，Java 通过 `ENGINE_BASE_URL` 调用。开发时两个目录并列运行；部署时可分别打包容器。

## 3. Spring Boot 设计

### 3.1 依赖规划

在现有 `spring-boot-starter-webmvc` 基础上增加：

- `spring-boot-starter-validation`：DTO 校验；
- `spring-boot-starter-data-jpa`：任务元数据持久化；
- `flyway-core` 与 MySQL Flyway 模块：Schema 版本化；
- `spring-boot-starter-actuator`：健康检查；
- `testcontainers-mysql`：集成测试；
- `spring-boot-starter-test`：测试统一入口，替换或核对当前生成器给出的测试依赖名称。

MVP 不加入 Spring Security 登录流程；但 Controller 不能接受任意文件路径，下载必须以数据库 artifact ID 查找。准备公开部署前必须新开认证规格。

### 3.2 应用用例

- `CreateGenerateJobUseCase`
- `CreateOptimizeJobUseCase`
- `GetJobUseCase`
- `ListJobsUseCase`
- `GetLessonResultUseCase`
- `ListArtifactsUseCase`
- `DownloadArtifactUseCase`
- `DispatchQueuedJobsUseCase`
- `ReconcileRunningJobsUseCase`

Controller 只负责协议转换；事务与状态机放在 application 层；JPA Entity 不直接返回前端。

### 3.3 异步执行

创建接口只完成：校验 → 保存输入/文件 → 插入 `QUEUED` → 返回 202。

后台派发器按 `created_at` 获取队首任务，并使用数据库原子更新把 `QUEUED` 抢占为 `DISPATCHING`。MVP 全局并发为 1。成功提交 Python 后记录 `engine_run_id` 并进入 `PREPROCESSING` 或 `RUNNING`。

`ReconcileRunningJobsUseCase` 周期查询 Python；每次响应以乐观锁更新状态、阶段和用量，并追加去重事件。终态后登记产物。Java 重启时同一对账器继续处理未终态任务。

禁止使用 Controller 请求线程等待整个 LangGraph；禁止只靠 `@Async` 内存 Future 保存任务状态。

### 3.4 SSE

`GET /api/v1/lesson-jobs/{jobId}/events` 使用 `SseEmitter`：

- 首次连接先发当前 snapshot；
- 后续发 `job.progress`、`job.terminal`；
- 客户端传 `Last-Event-ID` 时从 `lesson_job_event.sequence_no` 补发；
- 心跳 15 秒；
- 断开不影响任务；
- 前端 SSE 失败后改为查询详情。

## 4. Python Engine 设计

### 4.1 Web 包装原则

新增 `paper4_pipeline.web_api`，只调用正式 `PipelineService`，不能复制 graph。内部 API 接收 snake_case 的 canonical payload；Java Adapter 负责 camelCase ↔ snake_case 映射。

Python 任务执行使用单独 worker 进程或受控 `ProcessPoolExecutor(max_workers=1)`，不直接使用 FastAPI `BackgroundTasks` 承担长时间 LangGraph。任务真实状态仍来自 trace/result 文件。

### 4.2 生成路径

```text
GenerateRequest
→ Java DTO 校验和快照
→ EngineGenerateRequest
→ LessonTask(mode=generate)
→ PipelineService.run
→ PipelineResult + manifest
```

Java 不能自行拼完整 `LessonPlanDocument`，也不能解释 Critique 生命周期。

### 4.3 Word 优化路径

```text
OptimizeRequest + original.docx
→ 文件安全验证
→ OOXML 内容抽取（段落、标题、表格、列表）
→ RawLessonDocument
→ DocxNormalizer（结构化、可审计、有限重试）
→ LessonPlanDocument
→ LessonTask(mode=optimize, initial_plan=...)
→ 现有 Judge → Critics → Validator → Rewriter 闭环
→ 标准模板 Word
```

`DocxNormalizer` 是输入适配器，不是新的 Critic，也不参与最终评分。它必须记录 Prompt 版本、输入文件哈希、解析警告、模型用量和结构化结果。规范化后的 metadata 强制使用用户确认的科目、年级、课题和课时。

### 4.4 DOCX 安全与解析

- 同时检查文件扩展名、Content-Type、ZIP magic 和 OOXML 必需项；
- 拒绝宏文档、OLE 对象、外部关系、加密包；
- 解压前检查文件数量、压缩比、单文件大小和总展开大小；
- 解析段落、样式名、表格坐标、合并单元格文本和列表；
- 图片 OCR、公式语义恢复、批注和修订记录列为后续增强；MVP 遇到时产生 warning；
- 原文件只读保存，规范化数据单独保存。

## 5. 数据与文件边界

MySQL 用于过滤、排序、恢复和权限判断，因此存储任务摘要、状态、用量、错误码、请求快照 JSON 与产物索引。MySQL 原生 JSON 可校验 JSON 值，但 JSON 列本身不直接建立普通索引；高频查询字段必须是普通列。

本地 Storage 根目录结构：

```text
storage/
└─ jobs/<jobId>/
   ├─ input/original.docx
   ├─ input/request.json
   ├─ normalized/initial_plan.json
   └─ engine/<engineRunId>/...正式 artifacts...
```

数据库只保存相对 `storage_key`，不保存 C 盘绝对路径。Storage Adapter 解析并验证路径始终位于配置根目录内。

## 6. 状态机与一致性

允许迁移：

```text
QUEUED -> DISPATCHING
DISPATCHING -> PREPROCESSING | RUNNING | FAILED
PREPROCESSING -> RUNNING | FAILED
RUNNING -> EXPORTING | COMPLETED | NEEDS_HUMAN | FAILED
EXPORTING -> COMPLETED | NEEDS_HUMAN | FAILED
```

终态不可迁出。每次迁移在同一数据库事务内更新 job 并插入 event。Python 状态查询必须幂等。若 Java 不确定提交是否成功，使用同一个 `jobId` 重试内部创建接口；Python 必须返回已有 run，而不是再启动一个。

## 7. 前端技术计划

- Vue 3、TypeScript、Vite；
- Vue Router：生成、优化、任务详情、历史列表；
- Pinia：只存任务摘要、表单草稿和连接状态；大型教案结果不做全局常驻；
- Element Plus 提供表单、上传和基础无障碍，主题由自定义设计令牌覆盖；
- ECharts 仅用于八维雷达图；
- Axios 或统一 fetch client，自动处理 Problem Details；
- 原生 Vue Transition 与 CSS 动效，不为动画引入重量级运行时。

## 8. 配置

Spring Boot：

```yaml
app:
  engine-base-url: http://127.0.0.1:8001
  storage-root: ./var/storage
  max-upload-bytes: 20971520
  max-concurrent-jobs: 1
  artifact-retention-days: 30
```

Python：沿用 `DEEPSEEK_API_KEY` 与 `DEEPSEEK_BASE_URL`。Spring、Vue、MySQL 均不得获得 Key。

## 9. 测试策略

### Java

- 领域状态机单测；
- Controller MockMvc 契约测试；
- EngineClient WireMock 测试；
- MySQL Testcontainers + Flyway 集成测试；
- 文件上传攻击样例测试；
- 幂等与重复派发并发测试。

### Python

- DOCX fixture 提取测试；
- ZIP bomb/Zip Slip/伪装文件拒绝测试；
- Engine API Schema 测试；
- 规范化器契约测试使用保存的结构响应，不调用真实模型；
- 现有 90 项 Paper#4 回归必须继续通过。

### Vue

- Vitest：表单、状态映射、错误消息；
- MSW：API/SSE 模拟；
- Playwright：生成、上传优化、刷新恢复、下载四条关键路径；
- `prefers-reduced-motion` 与键盘操作检查。

### 真实验收

自动测试通过后，使用一个固定生成任务和一个固定 Word 优化任务真实调用 API。保存输入、版本、模型调用次数、费用、输出 Word 与人工检查结果。不得让 CI 调用付费模型。

## 10. 部署阶段

### MVP 本地

- Vue dev server；
- Spring Boot；
- Python Engine；
- MySQL；
- 本地 Storage。

### 演示部署

- Nginx 托管 Vue 并反代 Spring；
- Spring 与 Python 分容器；
- MySQL 独立卷；
- Storage 独立卷；
- Python 只监听内网；
- 单 worker 保持费用和并发可控。

### 扩展触发条件

当需要多用户、超过 2 个并发、跨机器恢复或任务峰值排队时，再引入 Redis/Celery 或等价任务队列和对象存储。接口不变，只替换 JobDispatcher 与 StoragePort。

## 11. 实施顺序

1. 冻结公开与内部契约；
2. 建 MySQL migration 和 Java 状态机；
3. 建 Python Engine API 的 generate 垂直切片；
4. 完成 Vue 生成流程；
5. 打通产物下载与进度；
6. 实现 DOCX 安全抽取与规范化；
7. 打通优化流程与对比展示；
8. 做失败恢复、安全、E2E 和真实验收；
9. 最后做视觉细化，避免用动画掩盖未完成业务。
