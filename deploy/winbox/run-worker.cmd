@echo off
rem Colophon SAM 3.1 worker on winbox. Started by start-worker.ps1 (never at boot/logon).
rem Copy to C:\ProgramData\colophon\run-worker.cmd. Extra arguments are passed to the worker.
setlocal
set "ROOT=C:\ProgramData\colophon"
if "%COLOPHON_WORKER_PY%"=="" set "COLOPHON_WORKER_PY=%ROOT%\worker_sam.py"
set "COLOPHON_SAM_CKPT=%ROOT%\models\sam3.1_multiplex_fp16.safetensors"
set "HF_HUB_OFFLINE=1"
set "PYTHONUNBUFFERED=1"
set "PYTHONWARNINGS=ignore"
call "%ROOT%\venv\Scripts\activate.bat"
cd /d "%ROOT%"
echo [%date% %time%] run-worker.cmd: starting %COLOPHON_WORKER_PY% >> "%ROOT%\worker.log"
python "%COLOPHON_WORKER_PY%" --coordinator http://hub:8101 --name winbox --ckpt "%COLOPHON_SAM_CKPT%" %* >> "%ROOT%\worker.log" 2>&1
echo [%date% %time%] run-worker.cmd: worker exited with code %ERRORLEVEL% >> "%ROOT%\worker.log"
endlocal
