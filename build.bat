@echo off
REM Builds dist\T-Music.exe. Requires Python 3.10+ on the build machine only;
REM the resulting .exe runs on any Windows 10/11 PC with nothing installed.
setlocal
cd /d "%~dp0"
if not exist .venv (
    python -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat || goto :error
python -m pip install --upgrade pip || goto :error
pip install -r requirements-build.txt || goto :error
python build.py || goto :error
echo.
echo Done! Your program is at dist\T-Music.exe
pause
exit /b 0
:error
echo Build failed.
pause
exit /b 1
