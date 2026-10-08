# Security Policy

## 敏感信息范围

本项目处理的敏感信息包括但不限于：

- `DEEPSEEK_API_KEY`、数据库口令、`ENGINE_INTERNAL_TOKEN`；
- 私钥、证书、云服务凭据；
- 教师上传的 Word、学生信息、真实课堂材料；
- `trace.jsonl`、`run_result.json`、模型请求/响应和费用记录；
- MySQL 数据文件、备份、日志与本机绝对路径。

## 本地配置

只从 `.env.example` 复制变量名。真实值写入 `.env`、操作系统环境变量或部署平台 Secret，禁止写进源码、Prompt、截图、Issue 或提交记录。

Python 与 Spring Boot 的 `ENGINE_INTERNAL_TOKEN` 必须相同，并使用随机长字符串。FastAPI 内部接口应只监听 `127.0.0.1` 或受信任的内部网络；不要直接暴露到公网。

## 文档与数据隐私

上传真实教案前应删除学生姓名、联系方式、成绩、健康信息等个人数据。系统运行目录默认被 Git 忽略，但操作者仍须检查待提交文件列表。不得将用户 Word、生成产物、trace 或数据库备份提交到公共仓库。

## 发布前检查

```bat
git status --short
git diff --cached --name-only
git grep -n -I -E "(API_KEY|PASSWORD|TOKEN|PRIVATE KEY)"
```

关键字命中并不一定代表泄漏；必须检查等号右侧是否是占位符或环境变量引用。还应检查大文件、Office 文档、截图和 Git 历史。

## 密钥误提交处置

1. 立即在 DeepSeek、数据库或对应服务中吊销并轮换；
2. 停止继续推送；
3. 使用 `git filter-repo` 等工具清理所有历史引用；
4. 强制更新远程前先通知协作者；
5. 重新扫描历史与发布产物。

仅从最新提交删除密钥无法使旧历史中的密钥失效。

## 支持范围

当前项目是研究原型，不承诺公网多租户安全。部署到公网前至少需要增加：身份认证、授权、HTTPS、速率限制、对象级访问控制、Secret Manager、审计告警、恶意文件扫描、备份加密与数据删除机制。
