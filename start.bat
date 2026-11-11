@echo off
REM Start HouseholdAI on Windows. First run creates a virtual environment and installs packages (a few minutes).
cd /d "%~dp0backend"
if not exist .venv (
  python -m venv .venv
  call .venv\Scripts\activate
  python -m pip install --upgrade pip
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate
)
echo.
echo Open http://localhost:8000 in your browser. Press Ctrl+C to stop.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
