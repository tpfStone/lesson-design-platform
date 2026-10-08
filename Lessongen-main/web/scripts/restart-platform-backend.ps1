$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $repoRoot

foreach ($keyName in @('DB_URL', 'DB_USERNAME', 'DB_PASSWORD', 'ENGINE_INTERNAL_TOKEN')) {
    $entry = Get-Content (Join-Path $repoRoot '.env') |
        Where-Object { $_.StartsWith("$keyName=") } | Select-Object -First 1
    if (-not $entry) { throw "Missing configuration: $keyName" }
    [Environment]::SetEnvironmentVariable($keyName, $entry.Substring($keyName.Length + 1), 'Process')
}
$env:FRONTEND_ORIGIN = 'http://127.0.0.1:5177'

Push-Location (Join-Path $repoRoot 'web')
try {
    & .\mvnw.cmd -DskipTests package
    if ($LASTEXITCODE -ne 0) { throw 'Java build failed; the old backend is still running' }
} finally {
    Pop-Location
}

$listener = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($listener) {
    $ownerId = $listener.OwningProcess
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ownerId"
    if ($process.Name -notin @('java.exe', 'javaw.exe') -or
        $process.CommandLine -notmatch 'LesoongenApplication|Lesoongen-0\.0\.1-SNAPSHOT\.jar|Lessongen-main[\\/]web') {
        $process | Select-Object ProcessId, Name, CommandLine | Format-List
        throw 'Port 8080 belongs to another process; nothing was stopped'
    }
    Stop-Process -Id $ownerId
    Write-Host "Stopped old Lessongen backend PID $ownerId"
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        if (-not (Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 500
    }
    if (Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue) {
        throw 'Port 8080 is still busy; check the old Java terminal'
    }
}

Write-Host 'Starting updated Java backend. Keep this window open.'
& (Join-Path $repoRoot 'web\scripts\start-backend.cmd')
