@echo off
cd /d "%~dp0"
where py >/dev/null 2>&1
if %errorlevel%==0 (py kanban.py) else (python kanban.py)
if errorlevel 1 pause
