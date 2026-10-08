# 灵犀教案（Lesoongen）

面向教师和师范生的 Paper#4 多智能体教案 Web 工作台。MVP 只做两件事：从教学信息生成教案，以及上传 `.docx` 原稿后优化教案。浏览器不接触模型 Key、Prompt 或磁盘路径。

## 系统结构

```text
Vue 3 / TypeScript（表单、真实进度、结果预览）
          │ /api/v1 + SSE
Spring Boot 4（公开 API、任务状态、MySQL、文件归属）
          │ /internal/v1 + 内部 Token
FastAPI（持久化单工作器、DOCX 输入适配器）
          │
现有 PipelineService / LangGraph / DeepSeek V4 Flash
```

- MySQL 只保存任务、事件、文件元数据与哈希；教案、trace 和上传文件放在受控文件存储。
- 本机默认运行数据写入项目内被 Git 忽略的 `var/`；仍可用环境变量覆盖。
- 创建接口立即返回 `202`，Spring 调度器异步提交并对账；MVP 同时只运行一个付费任务。
- 优化先做 OOXML 安全检查与定位抽取；系统原样导出的 Word 可经哈希校验直接恢复结构化原稿，其他 Word 由结构化 Agent 处理，再进入真实 graph。优化任务不会因初稿评分达标就跳过审查。
- 结果页展示审查意见、裁决、改写轮次和原稿/交付稿的栏目对比；`optimization_report.json/.md` 提供完整过程。若内容未改动，会明确标为“未修改”，不会把模型评分波动称为优化效果。
- 生产代码没有 Mock Agent 或固定教案分支；自动测试的替身只隔离外部付费 API。

## 目录

```text
frontend/                          Vue 工作台
src/main/java/.../api              公共 Controller、SSE、Problem Details
src/main/java/.../application      任务编排、状态对账、产物复制
src/main/java/.../domain           显式状态机与领域实体
src/main/java/.../infrastructure   MySQL/JPA、Python Client、本地存储
src/main/resources/db/migration    Flyway V1–V3
specs/001-lesson-plan-web          完整 Spec、契约、数据模型和任务清单
```

## 开始运行

完整步骤见 [Quickstart](specs/001-lesson-plan-web/quickstart.md)。推荐从 F 盘仓库根运行 `scripts\up.cmd`，Docker Compose 会用同一份根 `.env` 启动 MySQL、Python、Java、Vue，无需 Conda PR4 或手动对齐三个终端的 Token。访问 `http://127.0.0.1:5173`。仅在需要单独调试服务时按 Quickstart 的本地开发步骤启动。

## 验证

```bat
mvnw.cmd test
cd frontend
npm run format:check
npm test
npm run lint
npm run lint:openapi
npm run test:e2e
npm run build
npm audit --audit-level=high
```

Python 项目：

```bat
cd /d F:\comalesson\Lessongen
uv sync --project paper4_pipeline --locked --extra web --extra dev
paper4_pipeline\.venv\Scripts\python.exe -m pytest -q paper4_pipeline\tests
```

这些命令不会调用付费模型。执行真实生成或优化前，请确认账户余额和输入材料不含敏感数据。
