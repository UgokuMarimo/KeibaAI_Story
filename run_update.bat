@echo off
cd /d C:\KeibaAI
if not exist logs mkdir logs
echo [%date% %time%] Starting KeibaAI Model Update... >> logs\update.log
.venv\Scripts\python.exe src/update_model.py >> logs\update.log 2>&1
echo [%date% %time%] KeibaAI Model Update Finished. >> logs\update.log
