@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ==========================================
echo   AiRestro 本地工作台启动器（无需 Docker）
echo ==========================================
echo.

rem 1) 检查本机 PostgreSQL
netstat -ano | findstr ":5432" | findstr "LISTENING" >nul
if errorlevel 1 (
  echo [1/3] PostgreSQL 未运行，尝试自动启动...
  net start postgresql-x64-17 >nul 2>&1
  if errorlevel 1 (
    echo       自动启动失败，请手动打开服务窗口，启动 postgresql-x64-17 后再试。
    pause
    exit /b 1
  )
  timeout /t 2 /nobreak >nul
  echo       已启动。
) else (
  echo [1/3] PostgreSQL 运行中。
)

rem 2) 启动后端 + 前端
echo [2/3] 启动后端(8000)和前端(3000)...
python start_services.py
if errorlevel 1 (
  echo       启动失败，请确认已安装 Python 并查看 backend.log / frontend.log。
  pause
  exit /b 1
)

rem 3) 等待服务就绪并打开浏览器
echo [3/3] 等待服务就绪...
timeout /t 8 /nobreak >nul
start "" http://localhost:3000
echo.
echo 工作台已打开：http://localhost:3000
echo 后端接口文档：http://localhost:8000/docs
echo 关闭本窗口不影响服务运行。
pause