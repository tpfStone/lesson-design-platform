param()

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$envPath = Join-Path $repoRoot '.env'
$encoding = New-Object System.Text.UTF8Encoding($false)

function Read-DotEnvValue([string]$path, [string]$name) {
    if (-not (Test-Path -LiteralPath $path)) { return '' }
    foreach ($line in [System.IO.File]::ReadAllLines($path)) {
        if ($line.StartsWith("$name=")) {
            return $line.Substring($name.Length + 1).Trim().Trim('"').Trim("'")
        }
    }
    return ''
}

function New-LocalSecret {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Add-DotEnvValueIfMissing([string]$path, [string]$name, [string]$value) {
    if (-not (Read-DotEnvValue $path $name)) {
        [System.IO.File]::AppendAllText($path, "$name=$value`n", $encoding)
        return $true
    }
    return $false
}

$legacyRuntime = [System.IO.Path]::GetFullPath((Join-Path $repoRoot '..\runtime\lesoongen'))
$runtimeRoot = if (Test-Path -LiteralPath $legacyRuntime -PathType Container) {
    $legacyRuntime.Replace('\', '/')
} else {
    './runtime/lesoongen'
}

if (Test-Path -LiteralPath $envPath) {
    $changed = Add-DotEnvValueIfMissing $envPath 'LESSONGEN_RUNTIME_ROOT' $runtimeRoot
    $changed = (Add-DotEnvValueIfMissing $envPath 'PAPER4_WEB_STATE_ROOT' "$runtimeRoot/engine-state") -or $changed
    $changed = (Add-DotEnvValueIfMissing $envPath 'PAPER4_ARTIFACTS_ROOT' "$runtimeRoot/engine-artifacts") -or $changed
    $changed = (Add-DotEnvValueIfMissing $envPath 'LESSON_STORAGE_ROOT' "$runtimeRoot/web-storage") -or $changed
    if ($changed) { Write-Host 'Added the preserved runtime paths to the existing repository .env.' }
    else { Write-Host 'Repository .env already exists; credentials and runtime paths are unchanged.' }
    exit 0
}

$legacyEnv = Join-Path $repoRoot 'paper4_pipeline\.env'
$key = Read-DotEnvValue $legacyEnv 'DEEPSEEK_API_KEY'
if (-not $key -or $key.StartsWith('replace-with-')) {
    $secure = Read-Host 'DeepSeek API key (input hidden)' -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}
if (-not $key -or $key.Contains("`n") -or $key.Contains("`r")) {
    throw 'A non-empty, single-line DeepSeek API key is required.'
}

$token = Read-DotEnvValue $legacyEnv 'ENGINE_INTERNAL_TOKEN'
if (-not $token -or $token.StartsWith('replace-with-')) { $token = New-LocalSecret }

$lines = @(
    '# Local-only credentials. Do not commit this file.'
    "DEEPSEEK_API_KEY=$key"
    'DEEPSEEK_BASE_URL=https://api.deepseek.com'
    "ENGINE_INTERNAL_TOKEN=$token"
    "DB_PASSWORD=$(New-LocalSecret)"
    "MYSQL_ROOT_PASSWORD=$(New-LocalSecret)"
    "LESSONGEN_RUNTIME_ROOT=$runtimeRoot"
    "PAPER4_WEB_STATE_ROOT=$runtimeRoot/engine-state"
    "PAPER4_ARTIFACTS_ROOT=$runtimeRoot/engine-artifacts"
    "LESSON_STORAGE_ROOT=$runtimeRoot/web-storage"
)
[System.IO.File]::WriteAllText($envPath, (($lines -join "`n") + "`n"), $encoding)
Write-Host 'Created ignored repository .env. Existing paper4_pipeline/.env was not changed.'
Write-Host 'Docker uses MySQL on host port 3307; the old local MySQL service is untouched.'
