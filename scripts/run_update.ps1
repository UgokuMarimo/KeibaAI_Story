# PowerShell runner for KeibaAI Model Update
$ProjectRoot = Resolve-Path "$PSScriptRoot\.."
Set-Location $ProjectRoot

if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" | Out-Null
}

$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$Timestamp] Starting KeibaAI Model Update..." | Out-File -FilePath "logs\update.log" -Append
& ".venv\Scripts\python.exe" -u "src/update_model.py" *>> "logs\update.log"
"[$Timestamp] KeibaAI Model Update Finished." | Out-File -FilePath "logs\update.log" -Append
