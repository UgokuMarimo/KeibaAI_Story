@echo off
cd /d C:\KeibaAI
:: 仮想環境のPythonを使ってスケジューラーを起動し、ログを保存
.venv\Scripts\python.exe src/main_scheduler.py >> auto_exec.log 2>&1