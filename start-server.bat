@echo off
cd /d "%~dp0"
if not exist node_modules (
  echo Installing dependencies, this happens once...
  call npm install || goto :fail
)
if not exist dist\index.html (
  echo Building the app...
  call npm run build || goto :fail
)
call npm start
goto :eof
:fail
echo.
echo Something went wrong. Make sure Node.js 22.13 or newer is installed.
pause
