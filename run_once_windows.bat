@echo off
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" vibe_case_collector.py
) else (
  python vibe_case_collector.py
)
