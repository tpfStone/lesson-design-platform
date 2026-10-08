# Paper#4 运行指南

本文命令适用于 Windows CMD/Anaconda Prompt，但不依赖 Conda。唯一推荐的源码位置是 `F:\comalesson\Lessongen`；切勿从 C 盘旧副本启动。

## 1. 安装

```bat
cd /d F:\comalesson\Lessongen
uv sync --project paper4_pipeline --locked --extra web --extra dev
cd paper4_pipeline
```

只需先安装 uv：`.python-version` 固定 Python 3.11，uv 缺少该版本时会自动下载；`uv.lock` 固定 Python 依赖，虚拟环境始终创建在本仓库 `paper4_pipeline\.venv`。旧 PR4 环境及其 C 盘 editable 包不再参与运行。若要启动完整 Web，直接在仓库根运行 `scripts\up.cmd`（需 Docker Desktop），无需分别安装三端环境。

## 2. 环境变量

```bat
cd /d F:\comalesson\Lessongen
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup-local.ps1
cd paper4_pipeline
```

仓库根 `.env` 是唯一推荐的本地配置；脚本会优先复用本仓库旧 `paper4_pipeline/.env` 中的 Key/Token，否则隐藏式询问 Key。不会覆盖已存在的根 `.env`。至少需要：

```dotenv
DEEPSEEK_API_KEY=你的真实密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
ENGINE_INTERNAL_TOKEN=随机长字符串
```

`.env` 已被 Git 忽略。不要把真实 Key、Token 或用户教案提交到仓库。

## 3. 无费用检查

```bat
.venv\Scripts\python.exe -m paper4_pipeline.cli check
.venv\Scripts\python.exe -m pytest -q
```

这些命令不会调用付费模型。

## 4. 交互生成

```bat
.venv\Scripts\python.exe -m paper4_pipeline.cli generate
```

科目、年级、课题为必填；其余字段可回车跳过。系统在第一次付费调用前显示任务摘要并请求确认。

## 5. JSON 任务运行

```bat
.venv\Scripts\python.exe -m paper4_pipeline.cli run --task ".\examples\sample_task.json"
```

可用 `--output` 指定其他产物目录；不指定时写入 `PAPER4_ARTIFACTS_ROOT`。

## 6. 启动 Web 内部引擎

```bat
..\web\scripts\start-web-engine.cmd --check
..\web\scripts\start-web-engine.cmd
```

脚本强制使用 F 仓库 `.venv` 并确认 Provider 来自本仓库；还会检查 Key/Token 是否存在和配置文件路径。`--check` 不启动服务，也不调用付费模型，不打印密钥值。

默认地址为 `http://127.0.0.1:8001`，健康检查为：

```bat
curl http://127.0.0.1:8001/internal/v1/health
```

除健康检查外，内部接口要求 `X-Engine-Token`。不要将 8001 端口直接暴露到公网。

## 7. 产物

一次正常运行可能生成：

- `input_task.json`；
- `run_result.json`；
- `best_lesson_plan.json`；
- `best_lesson_plan.md`；
- `best_lesson_plan.docx`；
- `optimization_report.json/.md`；
- `manifest.json`；
- `trace.jsonl`。

失败时不保证存在 Word；有安全版本时可能导出 recovery 文件。上传原件不是优化结果。

## 8. 离线检查历史结果

```bat
cd /d F:\comalesson\Lessongen
paper4_pipeline\.venv\Scripts\python.exe scripts\audit-runtime.py F:\comalesson\runtime\lesoongen
cd paper4_pipeline
.venv\Scripts\python.exe -m paper4_pipeline.cli inspect --result "F:\comalesson\runtime\lesoongen\engine-artifacts\<run_id>\run_result.json"
.venv\Scripts\python.exe -m paper4_pipeline.cli export-process --run-dir "F:\comalesson\runtime\lesoongen\engine-artifacts\<run_id>"
.venv\Scripts\python.exe -m paper4_pipeline.cli analyze --artifacts "F:\comalesson\runtime\lesoongen\engine-artifacts"
```

`audit-runtime.py` 是只读验收：检查代表性的历史 JSON、Markdown、Word 包、manifest 哈希、引擎状态和上传原件，但不打印正文。新电脑没有历史目录时，把参数换成 `.env` 中的 `LESSONGEN_RUNTIME_ROOT`。

## 9. 常见问题

| 现象 | 检查项 |
| --- | --- |
| 401 | Spring 与 Python 的 `ENGINE_INTERNAL_TOKEN` 是否完全一致 |
| 402/余额错误 | DeepSeek 账户余额；不要靠重复运行解决 |
| 连接失败 | API 地址、代理、防火墙和 8001 端口 |
| 没有 Word | 运行是否形成可交付版本、是否安装 `python-docx` |
| Word 优化失败 | DOCX 是否加密/含宏/OLE、任务元数据是否与原稿一致 |
| `needs_human` | 查看停止原因、未解决意见和候选版本，不等同于进程崩溃 |

## 10. 正式验收

自动测试通过后，再执行一条受控真实生成和一条脱敏 Word 优化。检查 trace 中模型、Prompt 版本、真实尝试次数、token 和费用，并确认优化报告中的字段变化与下载 Word 一致。
