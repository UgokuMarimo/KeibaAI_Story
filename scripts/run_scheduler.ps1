# PowerShell runner for KeibaAI Main Scheduler
$ProjectRoot = Resolve-Path "$PSScriptRoot\.."
Set-Location $ProjectRoot

if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" | Out-Null
}

$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$Timestamp] Starting KeibaAI Main Scheduler..." | Out-File -FilePath "logs\scheduler.log" -Append
& ".venv\Scripts\python.exe" -u "src/main_scheduler.py" *>> "logs\scheduler.log"
"[$Timestamp] KeibaAI Main Scheduler Finished." | Out-File -FilePath "logs\scheduler.log" -Append
