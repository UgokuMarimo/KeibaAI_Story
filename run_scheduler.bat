@echo off
cd /d C:\KeibaAI
if not exist logs mkdir logs
echo [%date% %time%] Starting KeibaAI Main Scheduler... >> logs\scheduler.log
.venv\Scripts\python.exe src/main_scheduler.py >> logs\scheduler.log 2>&1
echo [%date% %time%] KeibaAI Main Scheduler Finished. >> logs\scheduler.log
