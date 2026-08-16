@echo off
setlocal
cd /d "%~dp0"

set "CLI=%LOCALAPPDATA%\Arduino15\arduino-cli.exe"
if not exist "%CLI%" (
  echo arduino-cli not found at %CLI%
  exit /b 1
)

set "ARDUINO_DIRECTORIES_DATA=%LOCALAPPDATA%\Arduino15"
set "ARDUINO_DIRECTORIES_USER=%USERPROFILE%\Documents\Arduino"

"%CLI%" compile --fqbn esp8266:esp8266:nodemcuv2 --warnings default --build-path "%~dp0firmware\build" "%~dp0firmware\KatBot"
exit /b %ERRORLEVEL%
