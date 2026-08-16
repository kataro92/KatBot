@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo Khong tim thay Python tren PATH. Cai Python 3.12+ roi chay lai.
  pause
  exit /b 1
)

if not exist "backend\.venv\Scripts\python.exe" (
  echo Tao moi truong ao backend\.venv ...
  python -m venv backend\.venv
  if errorlevel 1 (
    echo Tao venv that bai.
    pause
    exit /b 1
  )
)

call "backend\.venv\Scripts\activate.bat"
if errorlevel 1 (
  echo Khong active duoc venv.
  pause
  exit /b 1
)

echo Kiem tra / cai thu vien...
python -m pip install -q -r backend\requirements.txt
if errorlevel 1 (
  echo Cai thu vien that bai.
  pause
  exit /b 1
)

if not exist ".env" (
  if exist ".env.example" (
    copy /y ".env.example" ".env" >nul
    echo Da tao .env tu .env.example — sua neu can.
  )
)

set PORT=8080
if exist ".env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
    if /I "%%A"=="PORT" set "PORT=%%B"
  )
)

echo Giai phong cong %PORT% neu dang bi chiem...
powershell -NoProfile -Command ^
  "$p=%PORT%; Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $id=$_.OwningProcess; if ($id -and $id -gt 0) { Write-Host ('Kill PID '+$id); Stop-Process -Id $id -Force -ErrorAction SilentlyContinue } }"

echo.
echo Mo monitor: http://127.0.0.1:%PORT%
echo ESP ket noi: ws://^<IP-LAN-PC^>:%PORT%/ws/device
echo.
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port %PORT%
echo.
pause
