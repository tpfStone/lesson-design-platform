param([int[]]$Ports = @(5173, 8080, 3307))

$ErrorActionPreference = 'Stop'
$busy = $false
foreach ($port in $Ports) {
    $probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
    try {
        $probe.Start()
        $probe.Stop()
        continue
    } catch [System.Net.Sockets.SocketException] {
        $busy = $true
        $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
        $ownerId = if ($listener) { $listener.OwningProcess } else { 0 }
        if (-not $ownerId) {
            foreach ($line in (netstat -ano -p tcp)) {
                if ($line -match "^\s*TCP\s+\S+:$port\s+\S+\s+LISTENING\s+(\d+)") {
                    $ownerId = [int]$Matches[1]
                    break
                }
            }
        }
        $process = if ($ownerId) { Get-CimInstance Win32_Process -Filter "ProcessId=$ownerId" -ErrorAction SilentlyContinue } else { $null }
        $processName = if ($ownerId) { (Get-Process -Id $ownerId -ErrorAction SilentlyContinue).ProcessName } else { '' }
        $origin = 'unknown service'
        if ($process.CommandLine -like '*C:\Users\Administrator\Desktop\PR*') {
            $origin = 'C-drive legacy project'
        } elseif ($process.CommandLine -like '*F:\comalesson\Lessongen*') {
            $origin = 'F-drive project'
        } elseif ($process.Name -like '*docker*') {
            $origin = 'Docker or another Compose project'
        }
        Write-Host "[ERROR] Port $port is already in use (PID $ownerId, $processName, $origin). Stop that service before starting the F-drive stack."
    }
}
if ($busy) { exit 1 }
Write-Host "Ports $($Ports -join ', ') are available."
