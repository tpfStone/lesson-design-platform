param(
    [Parameter(Mandatory = $true)]
    [string]$SessionId,
    [string]$F3Url = "http://127.0.0.1:8003",
    [string]$F2Url = "http://127.0.0.1:8080"
)

$ErrorActionPreference = "Stop"
$result = Invoke-RestMethod "$F3Url/api/classroom/sessions/$SessionId/result" -TimeoutSec 240
$session = $result.session
if ($null -eq $session) { throw "F3 /result 缺少 session" }
if ($session.status -notin @("COMPLETED", "INTERRUPTED")) {
    throw "F3 session 尚未结束，当前状态：$($session.status)"
}

$source = $session.source
$f4SessionId = if ($source.session_id) { $source.session_id } else { $source.sessionId }
$f4LessonPlanId = if ($source.lesson_plan_id) { $source.lesson_plan_id } else { $source.lessonPlanId }
if (-not $f4SessionId -or -not $f4LessonPlanId) {
    throw "F3 结果缺少 F4 session/lesson plan 来源，不能安全回写"
}

$result | Add-Member -NotePropertyName f4SessionId -NotePropertyValue $f4SessionId -Force
$result | Add-Member -NotePropertyName f4LessonPlanId -NotePropertyValue $f4LessonPlanId -Force
$result | Add-Member -NotePropertyName executionBoundary -NotePropertyValue ([ordered]@{
    httpChain = "REAL"
    f4Provider = "generic_llm"
    f3ModelContent = $session.modelMode
    note = "Recovered from the formal F3 result API after the platform runner timed out."
}) -Force

$eventCount = @($result.events).Count
$issueCount = @($result.issues).Count
$summary = @"
# 课堂推演简报

- 课堂状态：$($session.status)
- 模型模式：$($session.modelMode)
- 课堂事件：$eventCount 个
- 发现问题：$issueCount 项
- F3 Session：$SessionId

本记录由 F3 正式结果接口恢复。
"@

$payload = [ordered]@{
    sessionRecord = $result
    summaryMarkdown = $summary
} | ConvertTo-Json -Depth 100

$lessonId = $session.lessonId
$saved = Invoke-RestMethod "$F2Url/api/platform/lessons/$lessonId/simulations" -Method Post -ContentType "application/json; charset=utf-8" -Body $payload -TimeoutSec 240

$saved | Format-List
