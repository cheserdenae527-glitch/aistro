@echo off
chcp 65001 >nul
cd /d "%~dp0desktop"
echo 正在启动 AiRestro 桌面端（首次会先拉起后端，请稍候）...
start "" node_modules\electron\dist\electron.exe .
exit /b 0