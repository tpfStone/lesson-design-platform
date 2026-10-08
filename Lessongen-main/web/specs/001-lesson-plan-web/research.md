# 技术研究与决策记录

## R-01 Java 与 Python 如何连接

决策：Spring Boot 调用 Python FastAPI 内部服务。

原因：现有 LangGraph、Pydantic、Prompt、Provider 和导出代码均在 Python。HTTP 契约能保持语言边界，支持独立测试和以后容器部署。

否决：

- Java `ProcessBuilder` 每次拉起 CLI：本地演示虽快，但进度、超时、并发、重启恢复和跨平台路径都脆弱；
- 在 Java 中重写 LangGraph：产生双实现和行为漂移；
- Vue 直接调用 Python：绕开数据库、文件权限和公开 API 边界，并暴露内部服务。

## R-02 为什么所有运行都异步

决策：公开创建接口返回 202，任务由后台派发器执行。

原因：一次运行可能多轮调用模型，现有默认最长运行时间达到 30 分钟；同步浏览器请求不适合承担该生命周期。刷新页面也不应中断任务。

否决：Controller 阻塞等待 Python 完成。

## R-03 是否现在引入 Redis/Celery

决策：MVP 不引入，但内部 API 和状态机按可替换队列设计。Python 使用独立 worker 进程；Java 使用 MySQL 持久化队列和周期对账。

原因：项目第一版默认并发 1，引入 Redis/Celery会显著增加部署和排错面。FastAPI 官方文档也提示重型后台计算更适合独立任务工具，因此即使 MVP 不上 Celery，也不能让长任务依附于 Web 请求生命周期。

升级条件：多机、多人并发、任务峰值、优先级队列或需要真正取消时。

## R-04 MySQL 存什么

决策：存结构化元数据与有限请求快照，不存二进制 Word 和完整 trace。

原因：任务状态需要事务、索引和恢复；DOCX/trace 是文件型产物，应由 StoragePort 管理。MySQL JSON 适合保存低频读取的请求快照并自动校验 JSON，但高频筛选字段仍拆为普通列。

否决：把整个 `run_result.json`、DOCX BLOB 和 trace 全塞入一张任务表。

## R-05 Word 如何进入优化管线

决策：安全抽取 + 结构化规范化 + 用户元数据覆盖，然后构造现有 `LessonTask(mode=optimize, initial_plan=...)`。

原因：`python-docx` 能提取段落与表格，却不能仅靠规则可靠理解不同学校模板里的“目标、活动、评价、板书”等语义；现有 LangGraph又严格要求 `LessonPlanDocument`。因此需要一个有 Schema、版本和 trace 的规范化器。

否决：

- 只把全文拼成字符串交给 Rewriter：破坏现有结构合同；
- 根据固定表格坐标硬编码：无法覆盖不同教案模板；
- 承诺保留原 Word 版式：MVP 输出走系统统一模板，避免样式复制和内容优化纠缠。

## R-06 是否现在上 RAG

决策：当前 Web MVP 不新增完整 RAG。课程标准和教材摘要先作为用户输入或后续附件能力，经现有异质知识包进入 Agent。

原因：Web 化的首要风险是异步任务、文件解析、结果交付和错误恢复；同时加入知识库切片、检索评价和权限会让变量失控。后续应以独立 Spec 添加“权威资料库”。

## R-07 前端方案

决策：Vue 3 + TypeScript + Vite + Pinia + Vue Router + Element Plus，八维图使用 ECharts。

原因：Vue 官方无 SSR 场景的快速入口使用 Vite；TypeScript 可让公开 OpenAPI DTO 与前端表单保持一致。MVP 不需要 Nuxt/SSR。

## R-08 进度展示

决策：SSE 为主、轮询降级。

原因：进度是服务端单向事件，SSE 比 WebSocket 更简单；最终一致性仍由 GET 任务详情保证。百分比来自阶段映射，不按等待秒数增长。

## R-09 Spring Boot 当前骨架

现状：工程使用 Java 17 和 Spring Boot 4.1.1，只含 Web MVC、MySQL runtime、Lombok 与测试依赖，尚无 JPA、Validation、Flyway、Actuator。编码第一步需先运行 Maven baseline 并核验依赖名是否符合当前 Spring Boot 版本，不在 Spec 阶段武断改动 POM。

## R-10 外部资料

- Spring Boot Reference：`https://docs.spring.io/spring-boot/`
- Vue Quick Start：`https://vuejs.org/guide/quick-start.html`
- Vue TypeScript：`https://vuejs.org/guide/typescript/overview`
- FastAPI Background Tasks caveat：`https://fastapi.tiangolo.com/tutorial/background-tasks/`
- MySQL JSON：`https://dev.mysql.com/doc/refman/8.4/en/json.html`

这些资料只支持框架和存储决策；Paper#4 的真实输入输出合同以本地 Pydantic 模型为唯一事实来源。
