# 数据模型

## 1. 原则

- MySQL 是 Web 任务元数据与状态的事实来源；
- Python `run_result.json` 是 Agent 闭环细节的事实来源；
- 文件存储是 DOCX、Markdown、JSON、trace 的事实来源；
- 数据库保存 `storage_key`，不保存操作系统绝对路径；
- Pydantic Schema 不在 Java 中逐字段镜像为数据库表。

## 2. `lesson_job`

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| `id` | `CHAR(26)` | ULID 主键，对外 jobId |
| `mode` | `VARCHAR(16)` | `GENERATE` / `OPTIMIZE` |
| `status` | `VARCHAR(24)` | Web 状态机枚举 |
| `status_version` | `BIGINT` | 乐观锁 |
| `subject` | `VARCHAR(64)` | 必填、可筛选 |
| `grade` | `VARCHAR(64)` | 必填、可筛选 |
| `topic` | `VARCHAR(255)` | 必填、可搜索 |
| `duration_minutes` | `SMALLINT` | 5–240 |
| `request_snapshot` | `JSON` | 规范化后的完整 Web 请求，不含文件与密钥 |
| `request_sha256` | `CHAR(64)` | 幂等和审计 |
| `idempotency_key` | `VARCHAR(128)` | 可空；24 小时窗口内唯一处理 |
| `retry_of_job_id` | `CHAR(26)` | 可空，自关联 |
| `engine_run_id` | `VARCHAR(255)` | 可空；Python run ID |
| `current_stage` | `VARCHAR(64)` | 公开阶段 |
| `current_round` | `SMALLINT` | 默认 0 |
| `progress_percent` | `TINYINT` | 0–100，来自真实阶段映射 |
| `pipeline_status` | `VARCHAR(24)` | completed/needs_human/failed，可空 |
| `stop_reason` | `VARCHAR(64)` | 原始 StopReason，可空 |
| `best_version_id` | `VARCHAR(64)` | 可空 |
| `last_version_id` | `VARCHAR(64)` | 可空 |
| `model_call_count` | `INT` | 默认 0 |
| `input_tokens` | `BIGINT` | 默认 0 |
| `output_tokens` | `BIGINT` | 默认 0 |
| `estimated_cost` | `DECIMAL(12,6)` | 默认 0 |
| `error_code` | `VARCHAR(64)` | 对外稳定错误码 |
| `error_message` | `VARCHAR(1000)` | 脱敏用户消息 |
| `owner_id` | `CHAR(26)` | MVP 可空，给认证扩展预留 |
| `created_at` | `DATETIME(6)` | UTC |
| `started_at` | `DATETIME(6)` | 可空 |
| `finished_at` | `DATETIME(6)` | 可空 |
| `updated_at` | `DATETIME(6)` | UTC |

索引：

- `idx_job_created_at(created_at desc)`；
- `idx_job_mode_status_created(mode, status, created_at desc)`；
- `idx_job_engine_run_id(engine_run_id)`；
- `idx_job_retry_of(retry_of_job_id)`；
- 幂等建议唯一键 `(idempotency_key, request_sha256)`，并由应用层限制 24 小时窗口。

## 3. `lesson_source_file`

一条优化任务最多一条 P0 输入文件；表结构允许未来多个附件。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `CHAR(26)` | 主键 |
| `job_id` | `CHAR(26)` | FK lesson_job，级联删除策略需谨慎 |
| `kind` | `VARCHAR(32)` | `ORIGINAL_LESSON_DOCX` |
| `original_filename` | `VARCHAR(255)` | 仅显示，不参与路径 |
| `media_type` | `VARCHAR(128)` | 检测值 |
| `size_bytes` | `BIGINT` | 最大 20 MiB |
| `sha256` | `CHAR(64)` | 完整性 |
| `storage_key` | `VARCHAR(512)` | 相对存储键 |
| `parse_status` | `VARCHAR(24)` | PENDING/PARSED/WARNING/FAILED |
| `parse_warnings` | `JSON` | 数组 |
| `normalized_plan_storage_key` | `VARCHAR(512)` | 可空 |
| `created_at` | `DATETIME(6)` | UTC |

唯一键：`(job_id, kind)`。

## 4. `lesson_artifact`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `CHAR(26)` | 公开 artifactId |
| `job_id` | `CHAR(26)` | FK |
| `artifact_type` | `VARCHAR(40)` | BEST_DOCX/BEST_MARKDOWN/BEST_JSON/RECOVERY_JSON/TRACE/PROCESS_REPORT 等 |
| `display_name` | `VARCHAR(255)` | 安全下载名 |
| `media_type` | `VARCHAR(128)` | MIME |
| `storage_key` | `VARCHAR(512)` | 相对键 |
| `size_bytes` | `BIGINT` | 大小 |
| `sha256` | `CHAR(64)` | 与 manifest 核验 |
| `status` | `VARCHAR(16)` | AVAILABLE/ERROR/MISSING |
| `error_message` | `VARCHAR(1000)` | 导出失败原因 |
| `created_at` | `DATETIME(6)` | UTC |

唯一键：`(job_id, artifact_type)`；索引：`idx_artifact_job(job_id)`。

## 5. `lesson_job_event`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `BIGINT AUTO_INCREMENT` | 主键 |
| `job_id` | `CHAR(26)` | FK |
| `sequence_no` | `INT` | 单任务严格递增，SSE event ID |
| `event_type` | `VARCHAR(64)` | job.queued/job.stage/job.terminal |
| `stage` | `VARCHAR(64)` | 公开阶段 |
| `round_index` | `SMALLINT` | 可空 |
| `version_id` | `VARCHAR(64)` | 可空 |
| `progress_percent` | `TINYINT` | 0–100 |
| `message` | `VARCHAR(500)` | 可公开、已脱敏 |
| `event_payload` | `JSON` | 小型扩展数据，不存完整教案/Prompt |
| `engine_event_key` | `VARCHAR(128)` | 去重键，可空 |
| `created_at` | `DATETIME(6)` | UTC |

唯一键：`(job_id, sequence_no)`、`(job_id, engine_event_key)`。

## 6. 状态迁移约束

应用层必须执行状态迁移表；数据库乐观锁阻止两个派发器同时更新。建议在领域对象中提供：

```text
job.dispatch()
job.markPreprocessing()
job.markRunning(stage, round, progress)
job.markExporting()
job.complete(pipelineSummary)
job.needHuman(pipelineSummary)
job.fail(error)
```

不得提供任意 `setStatus(String)`。

## 7. 结果内容策略

第一版不在 MySQL 冗余完整 `PipelineResult`。任务详情只返回摘要；结果端点由 Java 读取已登记的 best JSON，校验路径和 SHA-256 后映射为前端 DTO。若后续查询量证明文件读取成为瓶颈，再增加 `lesson_result_snapshot` JSON 缓存表，不能提前优化。

## 8. 保留与删除

- 默认保存 30 天；
- 清理先标记 `EXPIRED`，再删除文件，最后保留最小审计元数据；
- MVP UI 不提供删除按钮；
- 后续加入用户账户后，所有查询必须带 owner 条件。

## 9. Flyway

- `V1__create_lesson_job.sql`
- `V2__create_source_file_and_artifact.sql`
- `V3__create_job_event.sql`

Migration 必须支持全新数据库一次启动成功；测试不得依赖 Hibernate 自动建表。生产配置使用 `ddl-auto=validate`。
