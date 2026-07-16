@echo off
cd /d C:\keibaAI
if not exist logs mkdir logs
echo [%date% %time%] Starting KeibaAI Main Scheduler... >> logs\scheduler.log
call .venv\Scripts\activate.bat
python src/main_scheduler.py >> logs\scheduler.log 2>&1
echo [%date% %time%] KeibaAI Main Scheduler Finished. >> logs\scheduler.log
