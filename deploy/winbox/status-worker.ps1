# Is the Colophon worker running? Shows the process tree, GPU use and the end of the log.
#   ssh winbox powershell -NoProfile -ExecutionPolicy Bypass -File C:\ProgramData\colophon\status-worker.ps1
$root = 'C:\ProgramData\colophon'
$pidFile = Join-Path $root 'worker.pid'
if (Test-Path $pidFile) {
    $id = [int](Get-Content $pidFile | Select-Object -First 1)
    $p = Get-Process -Id $id -ErrorAction SilentlyContinue
    Write-Output ("pid {0}: {1}" -f $id, $(if ($p) { 'running since ' + $p.StartTime } else { 'NOT running (stale pid file)' }))
    Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $id -or $_.CommandLine -match 'worker_sam' } |
        Select-Object ProcessId, ParentProcessId, Name | Format-Table -AutoSize | Out-String | Write-Output
} else { Write-Output 'not running (no pid file)' }
& nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader
if (Test-Path (Join-Path $root 'worker.log')) { Get-Content (Join-Path $root 'worker.log') -Tail 15 }
