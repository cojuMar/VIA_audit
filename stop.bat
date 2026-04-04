@echo off
:: Project Aegis 2026 — Stop All Services
echo Stopping Project Aegis 2026...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Set-Location '%~dp0'; docker compose down"
echo.
echo All services stopped.
pause
