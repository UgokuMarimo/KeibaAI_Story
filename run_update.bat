@echo off
cd /d C:\keibaAI
if not exist logs mkdir logs
echo [%date% %time%] Starting KeibaAI Model Update... >> logs\update.log
call .venv\Scripts\activate.bat
python src/update_model.py >> logs\update.log 2>&1
echo [%date% %time%] KeibaAI Model Update Finished. >> logs\update.log
