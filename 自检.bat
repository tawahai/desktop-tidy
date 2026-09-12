@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
    python selftest.py
    goto done
)
where py >nul 2>nul
if %errorlevel%==0 (
    py selftest.py
    goto done
)
echo 没有找到 Python，请先安装 Python 3.9 或更高版本。
:done
echo.
pause
