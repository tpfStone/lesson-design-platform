# Paper#4 项目架构与开发说明

## 1. 项目目标

Paper#4 的目标不是让一个模型一次性“写一份看起来完整的教案”，而是建立一个可追踪、可复核、可开展实验的多角色迭代闭环。系统区分生成与优化两条入口，共享统一的教案数据合同、评价量表、意见生命周期和导出层。

## 2. 三层工程结构

### 2.1 Vue 前端

负责生成表单、Word 上传、任务进度、SSE 事件、结果预览、八维内部质量、实际修改证据和产物下载。前端不接触模型密钥、数据库密码、Prompt 或服务器磁盘路径。

### 2.2 Spring Boot 后端

公开 `/api/v1`，验证请求并立即创建异步任务；使用 MySQL 保存任务、事件、文件元数据与哈希；将上传件放入受控存储；使用内部 Token 调用 Python；对任务状态和产物执行最终对账。Flyway 负责数据库结构迁移。

### 2.3 Python 引擎

FastAPI 只提供内部接口。持久化单工作器避免同一进程内重复启动高成本任务；DOCX 适配层负责安全检查、文本/表格定位抽取和结构化；`PipelineService` 调用 LangGraph 工作流；导出层生成 JSON、Markdown、Word、manifest 与 trace。

## 3. 生成流程

```text
LessonTask
  → Design Architect（候选方案与选优）
  → Writer（v0）
  → deterministic rules
  → Judge
  → Router
  → three Critics
  → Validator
  → Rewriter
  → Verifier
  → Judge / Router（循环）
  → best-version selection
  → export
```

Design Architect 将发散设计与长篇成稿分开，避免 Writer 同时承担构思、选择和写作后退化成固定模板。Writer 的输出必须符合 `LessonPlanDocument`，才能进入后续流程。

## 4. Word 优化流程

```text
DOCX
  → OOXML safety inspection
  → deterministic extraction with locators
  → trusted restore（仅系统原样导出且哈希/manifest有效）
       或 segmented model normalization（外部Word）
  → imported v0 + baseline evaluation
  → mandatory critic review
  → Validator
  → per-critique targeted patch
  → baseline-relative hard-rule guard
  → Verifier / Judge / pairwise comparison
  → original or revised delivery + optimization report
```

外部 Word 不要求固定模板。解析器读取 OOXML 正文和表格，模型负责映射到规范教案结构。系统不会访问文档中的外部链接；图片不执行 OCR。

优化不能靠 Judge 随机分数上涨来宣称成功。交付层比较规范化原稿与候选稿的实际字段变化，并记录每条意见、裁决、修改路径、旧值摘要、新值摘要和未解决原因。

## 5. 三类 Critic 的关系

- Subject Critic：事实、概念边界、条件、教材范围、常见误概念；
- Pedagogy Critic：学习过程、认知进阶、支架、学生参与、差异化和课堂可行性；
- Alignment Critic：课程标准、学习目标、活动、学生产出与评价证据之间的一致性。

三者读取同一版本和各自知识包，不读取彼此本轮结论。当前代码在同一图节点内顺序调用，逻辑独立但尚未并发。Aggregator 只组合意见；Validator 才负责证据核验、去重、冲突和优先级。

## 6. Validator 与 Rewriter

Validator 为每条意见返回 `accept / reject / merge / defer`。程序额外执行确定性门禁：缺失权威课标时不能接受“补造课标”的意见，修改科目/年级/课题/课时的意见不能进入 Rewriter，阻塞硬规则的意见优先保留。

优化模式默认按意见做字段级 patch。每个 patch 必须指向真实 JSON Pointer，并产生可观察变化。外部原稿可能在进入系统时已有缺陷，因此 patch 采用“相对基线不退步”校验：允许尚未处理的旧缺陷继续存在，但禁止新增硬错误、破坏已通过检查或加重课时偏差。成功 patch 可逐条累计；一条失败不会抹掉其他成功修改。

## 7. 八维内部评价

Judge 使用冻结维度：课标对齐、知识准确、教学逻辑、课堂可行、差异教学、学生参与、评价设计、语言与格式。

程序重新计算平均分并应用空话、材料就绪度和学科深度上限。Router 综合硬规则、风险、总分、最低维度、回归、平台期、轮数和真实预算决定是否继续。模型的 `recommended_action` 只是证据，不是控制流。

## 8. 核心数据合同

- `LessonTask`：任务输入、模式、约束和可选初始教案；
- `LessonPlanDocument`：与 Word 版式无关的规范教案；
- `LessonPlanVersion`：版本、父版本、哈希、规则与评价；
- `CritiqueItem`：来源、维度、目标路径、证据和建议；
- `ValidationDecision`：四门核验与裁决；
- `RewriteOutcome`：新文档、实际修改映射和未解决项；
- `PipelineResult`：版本、意见、路由、用量、费用和产物总账。

模型对象采用 `extra=forbid`，防止字段静默漂移。步骤引用区分 `resource_ids` 与 `artifact_ids` 两个命名空间。

## 9. 可审计性

Prompt 文件独立版本化并计算 SHA-256。trace 记录角色、知识包、Prompt ID/版本/哈希、模型、响应标识、尝试次数、token、费用、耗时与输入输出摘要。manifest 保存交付文件 SHA-256。

失败但已有安全版本时，系统可交付 recovery 或 `needs_human` 结果；没有合格版本时不会用空白或上传原件冒充优化稿。

## 10. 数据库和文件存储

MySQL 负责可查询的业务状态；大文件与模型产物放文件存储。主要表包括任务、事件、源文件和产物。开发环境默认使用本地目录，生产环境可替换为对象存储，但必须保留所有权、哈希和下载鉴权。

## 11. 配置和实验边界

当前所有 Agent 默认使用同一底座模型，角色差异来自 Profile、Prompt、知识包、温度、可见字段和输出 Schema。这便于第一阶段控制变量。若研究底座模型异质性，应创建新的冻结配置和实验 ID，不应直接覆盖基线。

Paper#3 的 `SimulationReport → CritiqueBatch` 适配合同已经定义，但默认未接入主图。接入前需要冻结输出版本、证据 ID 和时间语义。

## 12. 发布与隐私

公开仓库只包含源码、Prompt、Schema、脱敏 fixture、Spec 和界面截图。`.env`、上传件、运行产物、trace、数据库和本机缓存全部忽略。真实人的实验还需要知情同意、最小化采集、匿名化、保留周期和删除流程。

## 13. 当前完成度

- 真实生成闭环：已实现；
- 外部 Word 通用结构化入口：已实现，图片 OCR 除外；
- 三 Critic / Validator / 定向改写 / Verifier：已实现；
- 三轮优化、质量门与 pairwise 候选比较：已实现；
- JSON/Markdown/Word/manifest/trace/优化报告：已实现；
- Spring Boot + MySQL + Vue：已实现本地 MVP；
- Paper#3 主图接入、RAG 权威课标库、用户登录与公网部署：待实现；
- 教师/师范生真实效果实验：待开展。
