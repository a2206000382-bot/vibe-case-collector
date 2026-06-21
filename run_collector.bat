@echo off
setlocal
cd /d "%~dp0"
python vibe_case_collector.py --once
pause
