# DisruptionIQ Startup Script
Set-Location -Path "\.."
Write-Host "[DisruptionIQ] Starting backend on http://localhost:8000..." -ForegroundColor Cyan
Write-Host "[DisruptionIQ] Interactive API Docs: http://localhost:8000/docs" -ForegroundColor Green
& ".\venv\Scripts\uvicorn.exe" backend.main:app --reload --host 127.0.0.1 --port 8000
