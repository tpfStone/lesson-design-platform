# 开发环境基线

> 本页是 2026-09-15 的历史快照，不是当前安装指南。当前唯一推荐入口见仓库根 [README](../../README.md)：`uv.lock`/`.venv` 或根目录 Docker Compose，不再依赖 Conda PR4。

2026-09-15 在交付目录实测：

- Windows 11 x64；
- Java 17.0.12；
- Maven Wrapper 3.9.16；
- Spring Boot 4.1.1；
- Node.js 24.14.0，npm 11.9.0；
- Vue 3.5.42，Vite 7.3.6，Vitest 5.0.0；
- Python 3.11.16，Conda 环境 `PR4`；
- MySQL 8.0.44；Docker CLI 28.5.1；
- Paper#4：110 tests passed；
- Spring Boot：10 个测试套件、19 项用例；2026-09-11 在 MySQL 8.0.44 Testcontainers 环境为 19/19 通过。2026-09-15 复测时 Docker Desktop 未运行，因此为 18 项通过、MySQL 容器迁移用例显式跳过；
- Vue：2 项单元测试、7 项浏览器 E2E 通过，OpenAPI lint、ESLint、Prettier 与生产构建通过；
- `npm audit`：0 vulnerabilities。

本机全局 Maven 配置不可复用。项目通过 `.mvn/maven.config`、`.mvn/settings.xml` 和 Maven Wrapper 固定项目内缓存与 Maven Central HTTPS，不修改全局配置。
