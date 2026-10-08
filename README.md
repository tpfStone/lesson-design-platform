# Lesson Design Platform

面向教师的 AI 教学设计平台，将教案评价、生成与优化、课堂模拟和协同修订整合到一个工作区。

当前版本为研究原型与本地部署开发版。四个模块的源码、测试、接口协议和依赖清单由本仓库统一管理。

## 四个模块

- **F1 智能评价** — [System-v1.2](System-v1.2/README.md)：教案评分、批注、改进建议、批量评审与对比。
- **F2 设计修改与总平台** — [Lessongen-main](Lessongen-main/README.md)：教案生成、优化、版本管理，以及 Vue/Spring Boot 统一平台。
- **F3 课堂推演** — [SimClass-main](SimClass-main/README.md)：多角色课堂模拟、过程记录与问题分析。
- **F4 协同共析** — [NoviceTeacher-AI-main](NoviceTeacher-AI-main/README.md)：逐节建议、教师采纳决策、多轮修订与版本回写。

## 目录与启动

四个项目保持原目录结构，以保留当前模块间的启动与导入路径。请按各模块 README 安装依赖、配置本地环境并启动服务；本仓库未提供新的统一一键启动器。

- [docs](docs/README.md)：公共问题与上下文协议、各模块 API 协议。
- `adapters/`：跨模块材料转换。
- `run_f3_demo.py`、`run_f4_to_f3*.py`：F4/F3/平台联调入口。
- `start_f3_demo.bat`：Windows 联调启动器。
- `f3_demo_config.example.json`：联调配置模板；使用时复制为本地 `f3_demo_config.json` 并填写当前教案和会话标识。
- [仓库管理说明](docs/REPOSITORY.md)：上传范围、原仓库历史与本地备份约定。

依赖声明及锁文件随源码提交。各模块的 `.env.example`、F4 的 `.env.zhipu.example` 可作为配置起点。F1 的 `config.yaml` 不含 API 密钥，实际密钥通过环境变量或本地设置提供。

## 本地数据与忽略规则

以下内容保留在使用者本机，不进入仓库：

- `.env`、`.api_key`、真实联调配置及其他密钥文件。
- SQLite 数据库、会话记录、运行日志、生成结果及批注输出。
- `.venv/`、`node_modules/`、Maven 下载缓存与构建产物。
- 大批教学资料、测试教案数据集、历史压缩包和恢复快照。

F1 的评分标准、知识库、必要的少量示例，以及其他模块的固定测试样例保留在仓库中。待评教案放入 `System-v1.2/data/plans/`，该目录仅跟踪占位文件。

在原开发机器上，教学资料位于 `教学资料/`，历史包及整理快照位于 `归档/`；这些目录不会随 GitHub 克隆下载。请独立备份运行数据，Git 提交不能代替数据库备份。

## 当前验证状态

首次总仓库导入已检查忽略规则、待提交文件、敏感值及嵌套仓库引用。此次导入没有运行完整构建、功能测试、模型请求或数据库迁移。

已知待处理项：F2 部分 Markdown 导出已调整，相关测试和旧运行文档的预期尚未同步。原模块 CI 文件保留在模块目录中，总仓库的根级 CI 尚未配置。
