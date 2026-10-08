# 基线审计（2026-09-22）

本页是时间点快照，不是持续监控。实施前应复核命令输出；路径、测试数和服务进程可能变化。只记录检查得到的事实，不把截图中的估计数字当作验收依据。

## 1. 代码与环境

- Git 仓库是 `F:\comalesson\Lessongen`，当前 `main` 有 4 个可见提交，HEAD 为 `665136e`。工作树有未提交的 Python、Java、Vue、配置与文档改动；不能直接覆盖或假设 GitHub 已包含这些修改。
- `C:\Users\Administrator\Desktop\PR\_4-reimplementatin\paper4_pipeline` 是另一套旧 Python 目录，不是该 Git 仓库；`C:\Users\Administrator\Desktop\PR\Web\Lesoongen` 是另一套旧 Java/Web 目录。`F:\comalesson\paper4_pipeline` 与 `F:\comalesson\web` 也是独立旧拷贝，并非仓库子目录或符号链接。
- PR4 Conda 环境中安装的 `comalesson-paper4` 是指向 C 盘 Python 目录的 editable 包。直接运行 `python -m paper4_pipeline...` 可导入旧代码。F 仓库 `web/scripts/start-web-engine.cmd` 会将仓库 `src` 放在 `PYTHONPATH` 前面并核验实际 Provider 路径；`--check` 在本次审计中显示 F 路径、Key/Token 存在和 F 配置文件存在。
- 审计时 8080 的 Java 进程 PID 15812 从 C 盘旧 Web 项目启动；8001 未运行。MySQL 本机 3306 可连接，Docker Desktop 服务未启动。由于服务会变化，启动前须重新核对，不能把健康检查 `UP` 当作“运行的是 F 仓库”。
- C 盘引擎默认状态/产物目录指向 `F:\comalesson\runtime\lesoongen`；F 仓库引擎默认指向仓库 `paper4_pipeline/var`。C 盘 Java 默认文件目录是旧 runtime；F Java 默认 `web/var/storage`。沿用旧数据库时，必须明确存储根目录，否则历史任务文件可能看似丢失。
- F 仓库 Python `.env` 已存在，Key 与内部 Token 在本次审计中均可用。它们与 C 盘 Python `.env` 对应值一致；不在文档、日志或 CI 输出其值。F Java 的 `DB_PASSWORD` 与 `ENGINE_INTERNAL_TOKEN` 默认值为空，IDEA/启动脚本须显式提供。F `compose.yaml` 把容器 MySQL 映射到主机 3307，而 Java 默认 URL 是 3306；不得同时假设两套数据库是同一个。
- C 盘旧 Java 配置曾把内部 Token 写作默认值；即使该目录不在 F Git 仓库，也应视为需要隔离的旧凭据，并在对外协作/发布前确认是否轮换。本文不记录其值。

## 2. 代码与验证

- F 仓库当前 Python 图在 `paper4_pipeline/src/paper4_pipeline/orchestration/graph.py`，包含 Design、Bootstrap、Judge、三 Critic、Validator、Rewriter、Verifier、Finalize 等节点；三 Critic 在一个节点内按列表顺序真实调用。现有 `knowledge/registry.py` 是按角色组织的版本化知识片段，不是可检索权威课标库。
- 生成模式当前允许 v0 的 Judge 分数、最低维度、硬规则与高风险检查通过后直接 `quality_passed`。2026-09-22 的运行 `20260922-132137-高中数学-高二-排列数与组合数-kqsvvz` 以 v0、内部总分 8.275 结束，没有调用 Critic；这符合现有路由，但不等于“经过多智能体独立审查”。优化模式已要求初稿先进入审查。
- F 仓库 Python 离线测试：171 passed（1 条依赖警告）；Java Maven 测试：24 tests、0 failures、1 skipped，跳过的是需要 Docker 的 MySQL 迁移测试；前端 Vitest：3 个文件、6 tests passed。上述都不证明多用户端到端或真实教学成效。
- 前端已有 Vitest、Playwright 配置和 1 个 E2E 流程文件，但 `stores/jobs.ts`、连接恢复、失败恢复和关键优化交互的覆盖仍须按行为盘点。仓库没有 `.github/workflows`；“三端测试全靠手动”应理解为缺少自动 CI，而非完全没有测试。
- Java `EngineContracts` 目前手写；Python FastAPI 可输出 OpenAPI；内部契约尚无稳定的单一生成源与漂移检查。Paper#3 有 `SimulationReport` 数据模型和 adapter，但 `enable_paper3` 尚未接入正式主图。

## 3. 与图片中旧判断的差异

| 图片表述 | 核实后的写法 |
| --- | --- |
| “163+21+6 测试全靠手动” | 本机此时为 Python 171、Java 24（1 skip）、前端 6；缺 CI 是事实，数字不是目标。 |
| “仅 2 个提交” | 当前 HEAD 可见 4 个提交，且工作树有未提交修改；仍需按模块整理提交。 |
| “graph.py 1400+ 行” | 文件约 1400 行量级，确实承担节点、路由、状态、trace 等多种职责；以职责边界而非行数作为拆分依据。 |
| “RAG、Paper#3、并发” | 均为候选能力，不应写成现有能力或没有成本/数据前提的必做项。 |

## 4. 复核命令与证据边界

```bat
cd /d F:\comalesson\Lessongen
git status --short
git rev-list --count HEAD
cd paper4_pipeline
..\web\scripts\start-web-engine.cmd --check
set "PYTHONPATH=F:\comalesson\Lessongen\paper4_pipeline\src;%PYTHONPATH%"
python -m pytest -q
cd ..\web
mvnw.cmd test
cd frontend
npm test
```

运行 Python 测试必须确认 `paper4_pipeline` 实际从 F 仓库导入；仅在 PR4 中直接执行 `python -m pytest` 可能误用 C 盘包。Java 的 Docker 集成测试需在 Docker 可用的独立验收中补跑。`--check` 仅校验当前命令窗口，不证明另一个已运行进程使用同一配置；进程/构建来源指纹列入 P0。

## 5. P0 环境实施记录（同日，尚非 Gate 通过）

- 已添加根目录一键启动入口、四服务 Compose、三个 Dockerfile、仓库根 `.env` 初始化/检查脚本、Python `.python-version` 与 `uv.lock`。本机用 uv 管理的独立 Python 3.11.15 在 F 盘新建 `.venv`，`sys.base_prefix` 和项目源码均指向 F，不再指向 Conda PR4；锁文件检查与 174 项 Python 离线测试通过。
- F 引擎 `--check` 确认 Provider、解释器、配置与数据根均来自 F；不打印 Key/Token。Java 本机 24 项通过、MySQL Testcontainers 1 项因 Docker daemon 未运行而跳过；前端 6 项单测、7 项浏览器 E2E、类型/格式/Lint/OpenAPI/构建通过。根 Compose 语法检查通过，但镜像构建、MySQL 迁移和全栈启动尚未实际验收。
- `.github/workflows/ci.yml` 已配置 Python、Java+Testcontainers、Vue+E2E、Docker build 和 secret scan；尚未推送到 GitHub，因此不能称 CI 已绿。一次 `Get-NetTCPConnection` 查询误报空端口；随后用 `netstat` 与实际绑定探针交叉核对，发现 5173 的 Node、8080 的 Java、8001 的 Python 正在监听，进程命令行来源因当前权限无法核实。根启动脚本现会在首次启动前用真实绑定探针拒绝 5173/8080 端口冲突，并报告可见 PID；不擅自停止用户进程。
- Docker 路线使用新的 MySQL 卷和仓库 `runtime/`，与旧 C/F 历史数据隔离。旧任务的读取/迁移、Java 构建来源指纹和真正 Docker 全栈验收仍留在 Gate 0A/0B，不能因为离线测试通过就勾选完成。

## 6. P01 验收执行记录（2026-09-22，提交后）

本机完成 P01（Phase 0B）代码级修复与验证，随后按模块提交；`tasks.md` 未勾选，原因见下。

- 修复阻断项：原 `paper4_pipeline/uv.lock` 与 `pyproject.toml` 不一致（`uv sync --locked --extra web --extra dev` 与 `uv lock --check` 均失败，CI Python job 第一步必红）。重新执行 `uv lock` 后 64 包锁定一致，`uv lock --check` 通过，`uv sync --locked` 干净安装成功。解析结果把 openai 3.17.0→3.16.2、langchain-openai 1.6.3→1.6.2 等 7 个包回退到 lock 版本；在该版本组合下全量测试通过。
- 验证结果（CI 同款命令，本机实测）：Python `uv run --no-sync python -m pytest -q` = **174 passed**；源码来源断言（`/paper4_pipeline/src/` 路径语义，Windows 下为反斜杠分隔）实际导入 `F:\comalesson\Lessongen\paper4_pipeline\src\paper4_pipeline\__init__.py`；Java `.\mvnw.cmd -B -ntp test` = **29 tests, 0 failures, 1 skipped**（跳过项为需 Docker 的 MySQL 迁移测试，CI ubuntu 会真实执行）；前端 vitest、typecheck、ESLint、Prettier、OpenAPI lint、build 与 Playwright msedge E2E（**7/7**）全部通过；根 `compose.yaml` 语法校验通过。
- 提交序列（本地 main，未推送）：`5d8d999` fix（引擎产物下载加固、合并意见错误上下文、Prettier）；`4183324` build（Compose/Dockerfile/CI/脚本/uv.lock/启动诊断/文档）；`5299e71` docs（002 规格）。提交前敏感扫描：无真实 Key/Token/PEM 模式（命中的 `DEEPSEEK_API_KEY=你的真实密钥` 均为占位符）。
- 仍留待确认：`paper4_pipeline/configs/deepseek_v4_flash.json` 的 writer/rewriter `max_tokens` 12288→24576 改动未提交（属问题 1 延续，未经验证，是否保留需项目负责人决定）。
- 未勾选 `tasks.md` 的原因：T006 依赖 Gate 0A（T001–T005 尚未验收）；Docker 镜像构建、全栈启动、GitHub Actions 平台运行与 gitleaks 扫描需要 Docker 引擎和 GitHub 远端，本机未执行；MySQL 迁移测试的真实执行只能在 CI ubuntu 完成。以上属平台级验证，非代码缺陷。

## 7. P0 最终验收（2026-09-23）

本节取代第 5–6 节中的“尚未验收”状态；前文作为过程记录保留，不回写历史事实。

- **唯一来源与可追踪构建：** 根 `scripts\up.cmd` 从干净工作树构建四服务。运行中的 Python `/internal/v1/health` 与 Java `/actuator/info` 均报告提交 `fad6425e7d3e`、`dirty=false`；Java 标记 `runtime=container`，Python 同时报告包版本、配置 SHA256、worker/config/model 已就绪。容器挂载源均为 `F:/comalesson/runtime/lesoongen -> /data`，不是 C 盘旧工程。
- **历史目录：** `scripts/audit-runtime.py` 只读验证代表性历史交付的 JSON、Markdown、DOCX 包和 manifest 哈希，以及 engine state、上传原件和 Web result。未移动或改写旧文件。审计同时发现 `my-first-live-run` 的旧 Word 与 manifest 哈希不一致；该 run 被跳过并保留原状，不能把它作为完整性样本。
- **本机离线回归：** Python **175 passed**；前端 **6** 项 Vitest、typecheck、ESLint、Prettier、OpenAPI lint、build 与 **7/7** Playwright E2E 通过；Java 全量回归与 MySQL 8.0.44 Testcontainers 通过。MySQL 专项还验证了 Flyway v1–v3 从空库迁移、外键约束拒绝坏数据，以及故意无效 V4 迁移必须抛出 `FlywayException`。
- **运行栈：** MySQL、engine、backend、frontend 四容器均为 `healthy`；后端 8080 和前端 5173 冒烟成功；Flyway 历史 v1–v3 均 `success=1`。健康与启动不调用 DeepSeek。
- **远端 CI：** GitHub Actions run [`35816829870`](https://github.com/CENG-ZH/Lessongen/actions/runs/35816829870) 的 Python、Spring Boot + real MySQL、Vue quality gates、Docker full-stack smoke 与 Secret scan 五个 job 全部成功。上一轮 Java job 有一次 runner 波动，重跑成功；工作流已增加失败 JUnit 注解，后续失败不再只显示 exit code。
- **提交与敏感信息：** 历史/索引规则扫描未发现 Key、GitHub Token、私钥或云凭据模式；gitleaks 远端 job 成功。被跟踪的 `.env` 仅为三个示例文件，真实 `.env`、DOCX、日志、运行目录均未入库。模型输出预算改动以独立提交 `0c90dce` 保留；P0 工程收口为 `fad6425`，失败诊断增强为 `2fb5eeb`，可分别回滚。

结论：Gate 0A 与 Gate P0 均通过。该结论只证明环境、构建、迁移、离线契约和启动链路可复现，不证明真实模型生成质量、优化成效或论文假设；后者仍属于 P1–P3。
