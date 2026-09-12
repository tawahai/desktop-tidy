@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在准备打包环境（需要联网，只装一次）...
python -m pip install --upgrade pyinstaller
echo.
echo 生成程序图标 ...
if not exist "app.ico" python dt_icon.py
echo.
echo 正在生成 exe ...
python -m PyInstaller --noconfirm --onefile --windowed --name "桌面收纳盒" --icon "app.ico" main.py
echo.
echo 完成！exe 在 dist 文件夹里，可以直接双击运行。
pause
