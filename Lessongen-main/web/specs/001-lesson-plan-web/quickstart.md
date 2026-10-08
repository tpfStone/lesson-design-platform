# Lessongen 启动指南

本仓库唯一推荐的源码入口是 `F:\comalesson\Lessongen`。旧 `C:\Users\Administrator\Desktop\PR` 是历史副本；启动前停止旧 C 盘服务，避免打开同一网址却访问到旧代码。不要删除旧数据库或教案文件。

## 一键启动（推荐）

安装并启动 Docker Desktop，然后在 Windows CMD / Anaconda Prompt 中执行：

```bat
cd /d F:\comalesson\Lessongen
scripts\up.cmd
```

首次运行会创建被 Git 忽略的仓库根 `.env`。脚本会复用现有 F 盘 `paper4_pipeline/.env` 中的 DeepSeek Key 和内部 Token；若无 Key，仅隐藏式询问一次。数据库密码由本机随机生成。随后 Docker 构建并启动 MySQL、Python 引擎、Spring Boot 和前端。访问 `http://127.0.0.1:5173`。启动本身不调用付费模型。

```bat
docker compose ps
docker compose logs --tail=100 engine backend
scripts\down.cmd
```

`down.cmd` 仅停止容器，不删除 MySQL 卷和运行数据。Python 与 Java 共同挂载 `.env` 中的 `LESSONGEN_RUNTIME_ROOT`；本机已有 `F:\comalesson\runtime\lesoongen` 时会继续读取该目录的历史上传件、JSON 和 Word，新安装才使用仓库 `runtime/lesoongen`。数据库在 Docker 命名卷。切勿用 `down -v` 或直接删卷来处理启动故障。MySQL 主机端口为 3307，后端为 8080；引擎 8001 不映射到主机。若 5173/8080/3307 被旧服务占用，请先确认来源并停止旧服务，不要盲目关闭进程。

仓库内旧 `web/compose.yaml` 只提供 MySQL，不要与根目录的全栈 `compose.yaml` 同时启动；两者都使用主机 3307，且数据库卷不同。

## 仅开发 Python 引擎时

只安装 uv 即可；它会按仓库 `.python-version` 自动准备 Python 3.11，不需要 Conda PR4：

```bat
cd /d F:\comalesson\Lessongen
uv sync --project paper4_pipeline --locked --extra web --extra dev
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup-local.ps1
web\scripts\start-web-engine.cmd --check
web\scripts\start-web-engine.cmd
```

启动脚本强制使用 `paper4_pipeline\.venv` 并打印实际 Provider 路径、配置路径和数据根（不打印密钥）。`--check` 是无费用检查。若曾在 PR4 安装 C 盘 editable 包，本命令也不会导入它。

## 单独调试 Java / Vue

推荐用 Docker Compose 保持数据库和 Python 引擎运行，修改 Java 时在 IDEA 打开 F 盘的 `web/pom.xml`，只重启 `backend` 服务（避免两个后端同时占用 8080）。如果必须在 IDEA 直接运行，先停止 Docker backend，并在 Run Configuration 中设置：`DB_URL=jdbc:mysql://127.0.0.1:3307/lesoongen?useUnicode=true&characterEncoding=utf8&serverTimezone=UTC`、`DB_USERNAME=lesoongen`、根 `.env` 里的 `DB_PASSWORD` 与 `ENGINE_INTERNAL_TOKEN`，以及 `ENGINE_BASE_URL` 指向可从主机访问的 Python 8001。注意 Docker 引擎默认不暴露 8001，故 IDEA 单跑后端时应按上节在主机启动 Python 引擎。

Vue 开发：

```bat
cd /d F:\comalesson\Lessongen\web\frontend
npm ci
npm run dev
```

Vue Vite 开发代理默认把 `/api` 发到主机 8080。不要把模型 Key 放进前端变量。

## 离线测试

```bat
cd /d F:\comalesson\Lessongen
paper4_pipeline\.venv\Scripts\python.exe -m pytest -q paper4_pipeline\tests
cd web
mvnw.cmd test
cd frontend
npm ci
npm test
npm run typecheck
npm run lint
npm run format:check
npm run lint:openapi
npm run build
```

本机 Docker 未启动时，Java Testcontainers 迁移测试会跳过；CI 要求该测试真实执行。以上测试不调用 DeepSeek。真实生成/优化前，请确认输入材料授权与账户余额。

历史文件只读验收：

```bat
cd /d F:\comalesson\Lessongen
paper4_pipeline\.venv\Scripts\python.exe scripts\audit-runtime.py F:\comalesson\runtime\lesoongen
```
