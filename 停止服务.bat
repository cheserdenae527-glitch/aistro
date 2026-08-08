@echo off
chcp 65001 >nul
echo 正在停止后端(8000)和前端(3000)...
powershell -NoProfile -Command "$pids = (netstat -ano | Select-String '(:8000 .*LISTENING|:3000 .*LISTENING)') | ForEach-Object { (($_ -split '\s+')[-1]) } | Sort-Object -Unique; if ($pids) { foreach ($p in $pids) { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue } ; Write-Host ('已停止进程: ' + ($pids -join ', ')) } else { Write-Host '没有运行中的前后端服务' }"
echo PostgreSQL 保持运行，如需停止请到 Windows 服务里操作。
pause