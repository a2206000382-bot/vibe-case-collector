@echo off
setlocal
cd /d "%~dp0\.."
py -3 vibe_case_collector.py
if errorlevel 1 (
  echo.
  echo 运行失败，请查看上方报错信息。
  pause
  exit /b 1
)
echo.
echo 运行完成。报告在 reports 文件夹中。
pause
