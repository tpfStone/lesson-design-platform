# F3 完整课堂模拟 API 说明

版本：3.0  
建议端口：`8003`  
入口：`app/api/classroom_api.py`

## 1. 设计边界

正式 API 不重写 SimClass 的课堂智能体逻辑，而是在原
`ClassState -> Manager -> FunctionExecutor -> Agent -> DialogueEntry`
循环外增加多会话、状态机、事件存储、结果与分析层。

每个 `sessionId` 持有独立 `Classroom`、`ClassState`、消息队列、
`EventStore` 和单 worker 线程。Manager/Agent 动作在 session 内串行执行，
不同 session 之间不共享 history/material/state。

## 2. 健康检查

### `GET /api/health`

兼容路径：`GET /health`

响应：

```json
{
  "status": "up",
  "service": "F3 Complete Classroom Simulation API",
  "version": "3.0",
  "port": 8003
}
```

## 3. 创建课堂

### `POST /api/classroom/sessions`

请求：

```json
{
  "lessonId": "LESSON-001",
  "versionId": "VERSION-001",
  "materials": [
    {
      "materialId": "m-1",
      "title": "一次函数定义",
      "teachingScript": "一次函数一般形式为 y=kx+b，其中 k 不等于 0。",
      "keyPoints": ["k 不等于 0"],
      "sourceSectionId": "sec-1",
      "metadata": {}
    }
  ],
  "modelMode": "MOCK",
  "timeoutSeconds": 15,
  "maxConsecutiveTimeouts": 3,
  "maxEvents": 60,
  "maxWallClockSeconds": 900,
  "requestKey": "client-request-001",
  "source": {"module": "F4"}
}
```

`modelMode` 可省略；服务端按 `F3_MODEL_MODE`，再按是否配置 `API_KEY` 决定。
显式请求 `REAL` 时，如果 provider 实际回退成 Mock，接口返回 503，禁止把 Mock
伪装为 REAL。

`requestKey` 为幂等键：同一服务实例内重复创建返回同一个 `sessionId`；服务重启后
也会从 `session.json` 恢复已见 requestKey。

首次创建返回 HTTP 201；幂等重放返回 HTTP 200，并带：

```json
{"idempotentReplay": true}
```

## 4. 查询状态

### `GET /api/classroom/sessions/{sessionId}`

状态枚举：

```text
READY | RUNNING | PAUSED | STOPPING | COMPLETED | INTERRUPTED | FAILED
```

关键字段：`lessonId/versionId/sessionId/modelMode/modelProvider/modelName`、
`startedAt/finishedAt/stopReason/pauseReason/limits/materials`。

## 5. 查询完整事件

### `GET /api/classroom/sessions/{sessionId}/events`

返回按 `sequence` 排序的结构化事件。每条事件包含：

- `eventId`、`sequence`、真实时间戳；
- `trigger`；
- `managerDecision`；
- `speaker/roleLabel/function/content`；
- `material`；
- `wallClockDurationMs`；
- `estimatedTeachingSeconds`（无可靠估算器时为 `null`）；
- `status/error`。

## 6. 发送消息

### `POST /api/classroom/sessions/{sessionId}/messages`

```json
{"message": "老师，k 可以等于 0 吗？"}
```

正式 API 为异步队列语义，HTTP 202 表示消息已接收，不代表该轮 Agent 已完成。
如果 session 因连续 Timeout 进入安全暂停，真实用户消息会恢复自主状态；如果是
人工 Pause，消息只排队，直到显式 Resume。

## 7. Pause / Resume / End

```text
POST /api/classroom/sessions/{sessionId}/pause
POST /api/classroom/sessions/{sessionId}/resume
POST /api/classroom/sessions/{sessionId}/end
```

- `pause`：下一轮起停止处理新触发；正在执行的 LLM 调用不会被粗暴中断；
- `resume`：人工暂停直接恢复；连续 Timeout 安全暂停会通过 `empty_enter` 语义
  清零 timeout 周期并恢复；
- `end`：进入 `STOPPING`，worker 收到停止信号后写为 `INTERRUPTED`，
  `stopReason=MANUAL_END`。

## 8. 动态设置

### `PATCH /api/classroom/sessions/{sessionId}/settings`

可修改：

```json
{
  "timeoutSeconds": 10,
  "maxConsecutiveTimeouts": 4,
  "maxEvents": 80,
  "maxWallClockSeconds": 1200
}
```

`timeoutSeconds` 从**下一次等待周期**生效，不强行中断当前已经开始的等待。

## 9. 分析

### `POST /api/classroom/sessions/{sessionId}/analyze`

运行独立 `IssueAnalysisAgent`。每条 issue 必须经过 `EvidenceValidator`；错误 eventId、
错误 sequence/speaker、正文中不存在的 quote、早于问题证据的 resolution、非法枚举或
无法映射的 target section 都会被拒绝。

验证失败只允许模型修复一次；仍失败的 issue 删除并写入 `warnings`。

证据通过后进入 `IssueConsolidator` 后处理：同一教案材料中重复出现的
`interaction_gap / assessment_gap / participation_imbalance` 会按“学生作答—反馈闭环缺失”
根因合并；随后按 `severity -> confidence -> 重复出现次数 -> evidence 数量` 排序，默认只保留
Top 5 供总平台/F4 消费。合并后的 evidence 仍全部来自已通过 EvidenceValidator 的真实事件，
并在输出前再次执行一次全局 EvidenceValidator。`actionItems[]` 只根据最终 Top 5 issues 生成。

## 10. 结果

### `GET /api/classroom/sessions/{sessionId}/result`

顶层合同：

```json
{
  "schemaVersion": "2.0",
  "session": {},
  "events": [],
  "statistics": {},
  "summary": {},
  "issues": [],
  "actionItems": [],
  "analysisWarnings": [],
  "artifacts": []
}
```

## 11. 下载结果

### `GET /api/classroom/sessions/{sessionId}/artifacts/{kind}`

支持：

```text
session_record
classroom_summary
issue_analysis
action_items
events
session
```

## 12. 旧 API 兼容层

迁移期保留：

```text
POST /api/classroom/start
POST /api/classroom/message
GET  /api/classroom/{sessionId}/state
```

旧 URL 现在映射到正式多会话服务，不再维护另一套全局 singleton 课堂。
`/message` 采用排队语义，返回 `queued`；需要实时拿本轮输出的调用方应迁移到
`events/result` 合同。
