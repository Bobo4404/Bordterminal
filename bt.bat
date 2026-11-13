@echo off
cd /d "%~dp0"
where py >NUL 2>&1
if %errorlevel%==0 (py bordterminal.py) else (python bordterminal.py)
if errorlevel 1 pause
