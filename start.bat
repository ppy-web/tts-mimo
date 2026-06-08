@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"
title Xiaomi MiMo Local TTS Service

echo ==========================================
echo   Xiaomi MiMo Local TTS Service
echo ==========================================
echo.

if not exist ".env" (
  echo [错误] 未找到 .env 文件。
  echo 请先复制 .env.example 为 .env，并填写 MIMO_API_KEY。
  echo.
  pause
  exit /b 1
)

if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
  set "PYTHON_EXE=python"
)

for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
  if /i "%%A"=="APP_HOST" set "APP_HOST=%%B"
  if /i "%%A"=="APP_PORT" set "APP_PORT=%%B"
)

if "%APP_HOST%"=="" set "APP_HOST=127.0.0.1"
if "%APP_PORT%"=="" set "APP_PORT=8000"

echo [信息] 使用 Python: %PYTHON_EXE%
echo [信息] 服务启动后访问: http://%APP_HOST%:%APP_PORT%/
echo [信息] WebSocket 地址: ws://%APP_HOST%:%APP_PORT%/virtualhuman/speech/synthesis/1103
echo.

"%PYTHON_EXE%" -m uvicorn app.main:app --host %APP_HOST% --port %APP_PORT%
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%EXIT_CODE%"=="0" (
  echo [错误] 服务启动失败，退出码: %EXIT_CODE%
  echo 请检查依赖是否已安装，或运行:
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
) else (
  echo [信息] 服务已退出。
)

echo.
pause
exit /b %EXIT_CODE%
