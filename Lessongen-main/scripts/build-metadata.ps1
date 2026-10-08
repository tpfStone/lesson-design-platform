param()

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$commit = 'unknown'
$dirty = 'unknown'

try {
    $commit = (& git -c "safe.directory=$repoRoot" -c core.excludesFile=/dev/null -C $repoRoot rev-parse --short=12 HEAD 2>$null).Trim()
    if (-not $commit) { throw 'empty Git commit' }
    $status = & git -c "safe.directory=$repoRoot" -c core.excludesFile=/dev/null -C $repoRoot status --porcelain --untracked-files=normal 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Git status failed' }
    $dirty = if ($status) { 'true' } else { 'false' }
} catch {
    $commit = 'unknown'
    $dirty = 'unknown'
}

Write-Output "$commit|$dirty"
