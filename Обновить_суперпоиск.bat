@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -X utf8 scripts\update_catalog.py
if errorlevel 1 (
  echo.
  echo Обновление прервано. Прежний каталог сохранён.
)
pause
