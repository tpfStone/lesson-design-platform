# F3 API 请求与响应样本

> 本文件基于本交付实际运行生成的 MOCK session，`sessionId=6355d918-0a67-4b09-996b-d7935fa493d3`。
> MOCK 仅用于功能验收，不代表真实模型效果。

## 1. 创建课堂

```http
POST /api/classroom/sessions
Content-Type: application/json
```

```json
{
  "lessonId": "LESSON-SAMPLE-001",
  "versionId": "VERSION-SAMPLE-001",
  "modelMode": "MOCK",
  "requestKey": "sample-20261005",
  "timeoutSeconds": 30,
  "maxConsecutiveTimeouts": 100,
  "maxEvents": 30,
  "maxWallClockSeconds": 60,
  "materials": [
    {"materialId":"m-define","title":"一次函数定义","teachingScript":"一次函数一般形式为 y=kx+b，其中 k 不等于 0。","keyPoints":["k 不等于 0","y=kx+b"],"sourceSectionId":"sec-1"},
    {"materialId":"m-example","title":"例题辨析","teachingScript":"通过 k=0 与 k≠0 的例子辨析一次函数和常函数。","keyPoints":["边界条件","反例辨析"],"sourceSectionId":"sec-2"}
  ]
}
```

响应中得到：

```json
{"sessionId":"6355d918-0a67-4b09-996b-d7935fa493d3","lessonId":"LESSON-SAMPLE-001","versionId":"VERSION-SAMPLE-001","modelMode":"MOCK"}
```

## 2. 用户消息

```http
POST /api/classroom/sessions/6355d918-0a67-4b09-996b-d7935fa493d3/messages
```

```json
{"message":"老师，k 可以等于 0 吗？"}
```

返回 HTTP 202，表示进入该 session 的串行消息队列。

## 3. Timeout 设置

```http
PATCH /api/classroom/sessions/6355d918-0a67-4b09-996b-d7935fa493d3/settings
```

```json
{"timeoutSeconds":0.02}
```

修改从下一等待周期生效。本样本随后发送 `继续` 唤醒已开始的 30 秒等待。

## 4. 最终结果

```http
GET /api/classroom/sessions/6355d918-0a67-4b09-996b-d7935fa493d3/result
```

```json
{
  "schemaVersion": "2.0",
  "status": "COMPLETED",
  "stopReason": "MANAGER_END_CLASS",
  "modelMode": "MOCK",
  "eventCount": 7,
  "roleCounts": {
    "teacher": 5,
    "assistant": 1,
    "inquisitive_mind": 1
  },
  "issues": 1,
  "analysisWarnings": [],
  "artifacts": [
    "events.json",
    "session.json",
    "issue_analysis.json",
    "action_items.md"
  ]
}
```

## 5. 下载

```text
GET /api/classroom/sessions/6355d918-0a67-4b09-996b-d7935fa493d3/artifacts/session_record
GET /api/classroom/sessions/6355d918-0a67-4b09-996b-d7935fa493d3/artifacts/classroom_summary
GET /api/classroom/sessions/6355d918-0a67-4b09-996b-d7935fa493d3/artifacts/issue_analysis
GET /api/classroom/sessions/6355d918-0a67-4b09-996b-d7935fa493d3/artifacts/action_items
GET /api/classroom/sessions/6355d918-0a67-4b09-996b-d7935fa493d3/artifacts/events
```
