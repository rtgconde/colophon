# Start the Colophon SAM worker on winbox, detached, so it outlives the SSH session.
#   ssh winbox powershell -NoProfile -ExecutionPolicy Bypass -File C:\ProgramData\colophon\start-worker.ps1
# Nothing persistent: no scheduled task, no service. A reboot or stop-worker.ps1 ends it.
# Win32_Process.Create (CIM) is used on purpose: a Start-Process child sits in the SSH session's
# job object and is killed when the session closes (tested 2026-11-02).
param(
    [string]$WorkerPy = '',      # testing only: run another script instead of worker_sam.py
    [string]$ExtraArgs = ''      # appended to the worker's command line, e.g. '--batch 8'
)
$ErrorActionPreference = 'Stop'
$root    = 'C:\ProgramData\colophon'
$pidFile = Join-Path $root 'worker.pid'
$stop    = Join-Path $root 'worker.stop'
$log     = Join-Path $root 'worker.log'

if (Test-Path $pidFile) {
    $old = Get-Content $pidFile | Select-Object -First 1
    if ($old -and (Get-Process -Id $old -ErrorAction SilentlyContinue)) {
        Write-Output "already running (pid $old); stop it first with stop-worker.ps1"
        exit 1
    }
    Remove-Item $pidFile -Force
}
$py = if ($WorkerPy) { $WorkerPy } else { Join-Path $root 'worker_sam.py' }
if (-not (Test-Path $py)) { Write-Output "missing $py - copy worker_sam.py there first"; exit 1 }
if (Test-Path $stop) { Remove-Item $stop -Force }   # a stale stop flag would end the new run at once

$cmd = "cmd.exe /c "
if ($WorkerPy) { $cmd += "set `"COLOPHON_WORKER_PY=$WorkerPy`"&& " }
$cmd += "`"$root\run-worker.cmd`" $ExtraArgs"
$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create `
        -Arguments @{ CommandLine = $cmd; CurrentDirectory = $root }
if ($r.ReturnValue -ne 0) { Write-Output "Win32_Process.Create failed: $($r.ReturnValue)"; exit 1 }
Set-Content -Path $pidFile -Value $r.ProcessId -Encoding ascii
Write-Output "started: cmd.exe pid $($r.ProcessId) (pid file $pidFile, log $log)"
Start-Sleep -Seconds 5
$kids = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($r.ProcessId)" | Select-Object ProcessId, Name
Write-Output ("children: " + (($kids | ForEach-Object { "$($_.Name)=$($_.ProcessId)" }) -join ' '))
if (Test-Path $log) { Get-Content $log -Tail 8 }
