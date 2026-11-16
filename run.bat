@echo off
rem Qwen Image Studio - double click to start (no console window)
rem 1) normal case: pythonw comes from PATH
rem 2) fallback: hand over to the .vbs launcher, which also probes fixed
rem    locations (WindowsApps / Programs\Python / C:\Python3xx) in case
rem    PATH is broken on some machine.
setlocal
cd /d "%~dp0"

where pythonw >nul 2>nul
if not errorlevel 1 (
    start "" pythonw "%~dp0app.py"
    exit /b 0
)

where python >nul 2>nul
if not errorlevel 1 (
    start "" python "%~dp0app.py"
    exit /b 0
)

for %%F in ("%~dp0*.vbs") do (
    start "" "%SystemRoot%\System32\wscript.exe" "%%~fF"
    exit /b 0
)

echo.
echo   Python was not found on this computer.
echo   Install Python 3.11+ from https://www.python.org/downloads/
echo.
pause
exit /b 1
