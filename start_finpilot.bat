@echo off
setlocal
cd /d "%~dp0"

echo [FinPilot] 清理可能残留的端口占用 (5174/8001)，避免双占导致地址漂移...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr /R ":5174[ ]" ^| findstr LISTEN') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr /R ":8001[ ]" ^| findstr LISTEN') do taskkill /F /PID %%a >nul 2>&1
timeout /t 2 >nul

echo [FinPilot] 启动后端 (uvicorn :8001)...
start "FinPilot-Backend" cmd /k ".venv\Scripts\uvicorn.exe finpilot_equity.web_app.main:app --host 0.0.0.0 --port 8001 --reload"

echo [FinPilot] 启动前端 (vite :5174)...
start "FinPilot-Frontend" cmd /k "cd frontend && npm run dev"

echo [FinPilot] 等待服务就绪...
timeout /t 6 >nul
start http://localhost:5174
echo [FinPilot] 已打开 http://localhost:5174
echo [FinPilot] 登录账号: admin@finpilot.ai
echo [FinPilot] 登录密码: 见 .env 中 FINPILOT_ADMIN_PASSWORD
endlocal
