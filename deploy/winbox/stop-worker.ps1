# Stop the Colophon SAM worker started by start-worker.ps1.
#   ssh winbox powershell -NoProfile -ExecutionPolicy Bypass -File C:\ProgramData\colophon\stop-worker.ps1 [-GraceSeconds 30] [-Force]
# 1. writes worker.stop (a worker that checks for it can finish its page and exit cleanly;
#    on Windows there is no SIGTERM for a detached session-0 process),
# 2. waits up to -GraceSeconds, 3. kills the whole tree by the recorded PID.
# A page killed mid-run is not lost: its lease expires after 20 min and it is re-queued.
param([int]$GraceSeconds = 30, [switch]$Force)
$root    = 'C:\ProgramData\colophon'
$pidFile = Join-Path $root 'worker.pid'
$stop    = Join-Path $root 'worker.stop'
if (-not (Test-Path $pidFile)) { Write-Output "no pid file - not running (or started some other way)"; exit 0 }
$id = [int](Get-Content $pidFile | Select-Object -First 1)
if (-not (Get-Process -Id $id -ErrorAction SilentlyContinue)) {
    Write-Output "pid $id is not running; removing stale pid file"
    Remove-Item $pidFile -Force; exit 0
}
if (-not $Force) {
    Set-Content -Path $stop -Value (Get-Date -Format o) -Encoding ascii
    $deadline = (Get-Date).AddSeconds($GraceSeconds)
    while ((Get-Date) -lt $deadline -and (Get-Process -Id $id -ErrorAction SilentlyContinue)) { Start-Sleep -Seconds 1 }
}
if (Get-Process -Id $id -ErrorAction SilentlyContinue) {
    & taskkill.exe /PID $id /T /F | Out-Null
    Write-Output "killed process tree of pid $id"
} else {
    Write-Output "worker (pid $id) exited on its own"
}
Remove-Item $pidFile, $stop -Force -ErrorAction SilentlyContinue
