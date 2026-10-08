# Python Engine 内部契约

## 1. 定位

该接口只服务 Spring Boot，不直接开放给浏览器。它把 Web 请求适配到现有 `PipelineService`，不复制 LangGraph、不改变 Agent 状态机，也不把 CLI 当作进程间协议。

基础地址：`http://127.0.0.1:8001/internal/v1`。部署时仅内网可达；除本机开发外要求 `X-Engine-Token`。请求与日志使用 Spring 产生的 `external_job_id` 作为 correlation id。

## 2. 端点

### `POST /runs/generate`

请求为 JSON：

```json
{
  "external_job_id": "01J...",
  "request_sha256": "64位小写十六进制",
  "task": {
    "mode": "generate",
    "subject": "化学",
    "grade": "高一",
    "topic": "酸碱中和反应",
    "duration_minutes": 45,
    "course_information": "",
    "textbook_version": "",
    "textbook_content": "",
    "curriculum_standards": [],
    "learning_objectives": [],
    "student_profile": "",
    "class_size": null,
    "available_resources": [],
    "additional_requirements": "",
    "lesson_style": "choose_the_best_fit_for_this_topic",
    "detail_level": "showcase"
  }
}
```

响应 `202`：

```json
{
  "engine_run_id": "20260910-...",
  "external_job_id": "01J...",
  "status": "queued",
  "created_at": "2026-09-10T12:00:00Z"
}
```

同一 `external_job_id` 重试必须幂等：任务摘要一致则返回原 `engine_run_id`；摘要不同返回 `409 ENGINE_IDEMPOTENCY_CONFLICT`。

### `POST /runs/optimize`

`multipart/form-data`：

- `request`：`application/json`，结构与生成一致，但 `mode=optimize`，增加 `optimization_focus[]` 与 `must_preserve_content[]`；
- `document`：原始 DOCX 二进制。

Python 先做安全校验和抽取，再由 `DocxNormalizer` 产生合法 `LessonPlanDocument`，最后设置 `LessonTask.initial_plan`。当前引擎不能直接把任意 Word 当作 `initial_plan`，本适配层是必须实现的新增能力。

### `GET /runs/{engineRunId}`

返回当前快照：

```json
{
  "engine_run_id": "20260910-...",
  "external_job_id": "01J...",
  "status": "running",
  "stage": "critics",
  "round_index": 1,
  "version_id": "v1",
  "progress_percent": 55,
  "pipeline_status": null,
  "stop_reason": null,
  "best_version_id": null,
  "last_version_id": "v1",
  "usage": {
    "model_call_count": 8,
    "input_tokens": 42000,
    "output_tokens": 9000,
    "estimated_cost": 0.04
  },
  "last_event_sequence": 17,
  "error": null,
  "updated_at": "2026-09-10T12:03:00Z"
}
```

Engine 状态取值：`queued/preprocessing/running/exporting/completed/needs_human/failed`。`progress_percent` 是公开阶段映射，不是按时间推测的模型百分比。

### `GET /runs/{engineRunId}/events?afterSequence=N`

返回有界 JSON 事件列表，而非内部 SSE：

```json
{
  "items": [
    {
      "sequence": 18,
      "event_type": "stage.changed",
      "stage": "validator",
      "round_index": 1,
      "version_id": "v1",
      "progress_percent": 64,
      "message": "正在校验并合并修改建议",
      "occurred_at": "2026-09-10T12:03:05Z"
    }
  ],
  "last_sequence": 18,
  "has_more": false
}
```

Spring 定期拉取、去重并写入 `lesson_job_event`，再以公开 SSE 推给浏览器。单次最多 100 条；`has_more=true` 时继续拉取。

### `GET /runs/{engineRunId}/result`

仅在已形成版本时返回 `200`，内容包括：

- `pipeline_status`、`stop_reason`；
- `best_version_id` 与 `last_version_id`；
- `best_lesson_plan`；
- 八维 `rubric_scores`、`overall_score`；
- `implemented_changes`、`unresolved_issues`；
- 优化任务的 `parse_warnings`；
- `artifacts[]` 元数据。

尚无版本返回 `409 ENGINE_RESULT_NOT_READY`。失败但有 recovery 时仍返回结果摘要与 recovery artifact。

### `GET /runs/{engineRunId}/artifacts/{artifactId}`

仅允许下载 manifest 中登记且属于该 run 的文件。响应二进制、MIME、长度、安全文件名和 `Digest`。Spring 拉取后写入自己的 `StoragePort` 并校验 SHA-256；浏览器不接触此端点。

### `GET /health`

返回进程、配置和工作器是否可接单；绝不返回 API Key。建议区分：

- `status=up`：HTTP 进程正常；
- `worker_ready=true/false`：工作器是否可派发；
- `model_configured=true/false`：仅表示变量存在，不验证或展示内容。

## 3. 状态与事件映射

| Engine stage | Web 文案 | 建议百分比区间 |
| --- | --- | --- |
| `queued` | 等待执行 | 0–5 |
| `docx_security_check` | 检查 Word 文件 | 5–10 |
| `docx_extract` | 读取原教案 | 10–16 |
| `docx_normalize` | 理解并结构化原教案 | 16–24 |
| `designer/writer` | 设计并撰写教案 | 10–30 |
| `judge` | 进行内部质量检查 | 30–40 |
| `critics` | 多角色审阅教案 | 40–58 |
| `validator` | 校验并合并修改建议 | 58–68 |
| `rewriter` | 根据有效意见优化 | 68–82 |
| `verifier` | 核对修改是否落实 | 82–88 |
| `export` | 生成结果文件 | 90–98 |
| terminal | 已完成/待复核/失败 | 100 |

重复轮次只能在相应区间内根据真实节点事件变化，不能每过若干秒自动增长。页面以阶段和轮次为主，百分比只作辅助。

## 4. 规范化器契约

`DocxNormalizer` 输出：

```text
NormalizedLessonInput
├─ source_sha256
├─ parser_version
├─ normalizer_prompt_version
├─ metadata_provenance       # 每个关键元数据来自 user/file/inferred
├─ raw_document              # 段落/表格的稳定编号与文本
├─ lesson_plan               # 严格 LessonPlanDocument
├─ preserved_content_map     # 必须保留项到原文位置
├─ warnings[]
└─ usage
```

约束：

1. 用户确认的 subject/grade/topic/duration 覆盖模型推断；
2. 不得补造课程标准、教材出处或页码；
3. 不能确定归属的原文进入附注/原始材料引用，不静默丢弃；
4. 结构输出先经 Pydantic 校验，最多两次结构修复；
5. 失败即 `DOCX_NORMALIZATION_FAILED`，不得构造空壳教案继续跑；
6. Prompt、响应、用量可审计，但公开接口只暴露 warning 和摘要。

## 5. 错误码

| HTTP | code | 含义/Java 动作 |
| --- | --- | --- |
| 400 | `ENGINE_INVALID_REQUEST` | 映射契约错误，任务失败并记录 correlation id |
| 409 | `ENGINE_IDEMPOTENCY_CONFLICT` | 停止重试，告警人工排查 |
| 413 | `DOCX_TOO_LARGE` | 向用户说明大小限制 |
| 415 | `INVALID_DOCX` | 文件类型、安全或 OOXML 校验失败 |
| 422 | `DOCX_NORMALIZATION_FAILED` | 原稿无法可靠变成结构化教案 |
| 401/403 | `MODEL_AUTH_FAILED` | 提示管理员检查模型配置 |
| 402 | `MODEL_BALANCE_EXHAUSTED` | 提示余额不足，可重新运行但不自动烧费重试 |
| 429 | `MODEL_RATE_LIMITED` | 有限退避后仍失败，提示稍后新建重试任务 |
| 502/503 | `MODEL_UNAVAILABLE` | 网络/上游不可用，按策略有限重试 |
| 500 | `ENGINE_INTERNAL_ERROR` | 返回脱敏摘要，保留服务端 traceback |

## 6. 超时与重试

- 连接超时 3 秒，普通状态查询读取超时 10 秒；
- 创建 run 的读取超时 30 秒，因为只入队、不运行完整模型；
- 仅对连接失败、502/503 和幂等的 GET/创建请求做指数退避；
- 402、401、403、409、415、422 不自动重试；
- Java 在“不确定 POST 是否已接收”时必须用同一 `external_job_id` 重试；
- 全链路模型任务无 HTTP 长连接，不设置一个覆盖整轮的请求超时。

## 7. 版本兼容

- Java 请求发送 `contract_version: "1"`（实现时加入公共 envelope）；
- Python 结果携带 `engine_version`、`schema_version`、`prompt_versions`；
- 增字段必须向后兼容；删除、改名或改变枚举语义必须升级 `/internal/v2`；
- CI 使用保存的双方契约 fixture 检查 camelCase/snake_case 映射。
