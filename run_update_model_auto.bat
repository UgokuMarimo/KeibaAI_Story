@echo off
cd /d C:\KeibaAI
:: 仮想環境のPythonを使ってモデル更新スクリプトを実行し、ログを保存
.venv\Scripts\python.exe src/update_model.py >> update_model_auto.log 2>&1