@echo off
chcp 65001 >nul
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "main.py"
    exit /b
)
where python >nul 2>nul
if %errorlevel%==0 (
    start "" python "main.py"
    exit /b
)
echo.
echo  没有找到 Python，请先安装 Python 3.9 或更高版本：
echo  https://www.python.org/downloads/
echo  安装时请勾选 "Add python.exe to PATH"
echo.
pause
