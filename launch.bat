@echo off
title NSE Market Intelligence Platform
cd /d "%~dp0"
echo ============================================
echo   NSE Market Intelligence Platform
echo ============================================
echo.
echo  Starting server...
echo.
echo  Local access:    http://localhost:8050
echo  Network access:  http://%COMPUTERNAME%:8050
echo.
echo  Opening browser automatically...
echo  Press Ctrl+C to stop the server.
echo ============================================
echo.
start "" http://localhost:8050
python app.py --host 0.0.0.0 --port 8050
echo.
echo  Server stopped.
pause
