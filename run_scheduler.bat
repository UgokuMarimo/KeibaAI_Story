@echo off
:: バッチファイルが存在するフォルダを作業ディレクトリに設定
cd /d "%~dp0"

:: 文字コードをUTF-8に設定（ログの文字化け防止）
chcp 65001 > nul
set PYTHONIOENCODING=utf-8

:: logs ディレクトリが存在しない場合は作成
if not exist logs mkdir logs

:: ログ開始メッセージ
echo. >> logs\scheduler.log
echo ================================================== >> logs\scheduler.log
echo [%date% %time%] Starting KeibaAI Main Scheduler... >> logs\scheduler.log

:: Pythonスクリプトの実行
"%~dp0.venv\Scripts\python.exe" -u "%~dp0src\main_scheduler.py" >> logs\scheduler.log 2>&1

:: ログ終了メッセージ
echo [%date% %time%] KeibaAI Main Scheduler Finished. >> logs\scheduler.log
echo ================================================== >> logs\scheduler.log

