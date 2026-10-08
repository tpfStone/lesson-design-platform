# 001 · 教案生成与优化 Web MVP

状态：`READY_FOR_REVIEW`
规格日期：2026-09-10
目标工程：仓库 `web/` 目录
生成引擎：仓库 `paper4_pipeline/` 目录

本目录是实现前的规格基线。当前只冻结产品边界、系统职责、契约、数据模型、交互与验收标准，不提前提交业务实现。

## 文档导航

1. [spec.md](./spec.md)：用户需求、范围、流程、验收条件；
2. [plan.md](./plan.md)：技术架构、服务边界、运行与安全方案；
3. [research.md](./research.md)：关键技术决策和被否决方案；
4. [data-model.md](./data-model.md)：MySQL 与文件存储模型；
5. [ui-spec.md](./ui-spec.md)：页面、组件、视觉和动效规范；
6. [contracts/openapi.yaml](./contracts/openapi.yaml)：Vue 调用 Spring Boot 的公开接口；
7. [contracts/python-engine-api.md](./contracts/python-engine-api.md)：Spring Boot 调用 Python 引擎的内部契约；
8. [tasks.md](./tasks.md)：按依赖排序的实施任务；
9. [quickstart.md](./quickstart.md)：规划中的本地启动与验收路径；
10. [checklists/requirements.md](./checklists/requirements.md)：进入编码前的规格检查表。

## 已冻结的核心决策

- Vue 只访问 Spring Boot，浏览器不能直接访问 Python 或 DeepSeek。
- Spring Boot 是公开 API、任务状态、文件元数据和访问控制的唯一入口。
- Python 服务包装现有 LangGraph，不在 Java 中重写 Agent 流程。
- 所有生成和优化都是异步任务，创建接口必须快速返回 `202 Accepted`。
- MySQL 保存可查询的任务/状态/事件/产物元数据；DOCX、Markdown、JSON、trace 等大文件进入文件存储抽象，MVP 使用本地目录。
- “上传 Word 优化”必须先经过 DOCX 安全校验、内容提取和结构化规范化，才能构造 `mode=optimize` 的 `LessonTask`。
- MVP 为单用户本地原型，不做登录、多人协作、在线富文本共同编辑、RAG 管理后台和 Paper#3 联动。
- 不引入 Mock Agent。离线测试可使用契约桩，但产品运行只接受真实引擎结果。

## Definition of Ready

`checklists/requirements.md` 中的架构与需求项已通过。项目展示名称、MVP 登录范围均已有默认值，可直接进入 `tasks.md` 的编码阶段；用户后续若改名或要求登录，再以独立变更调整，不阻塞首个垂直切片。
