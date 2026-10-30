@echo off
cd /d "%~dp0\.."
echo [DisruptionIQ] Starting backend on http://localhost:8000...
echo [DisruptionIQ] Interactive API Docs: http://localhost:8000/docs
.\venv\Scripts\uvicorn.exe backend.main:app --reload --host 127.0.0.1 --port 8000
