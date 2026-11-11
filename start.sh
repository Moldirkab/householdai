#!/usr/bin/env bash
# Start HouseholdAI on macOS / Linux. First run creates a virtual environment and installs packages (a few minutes).
set -e
cd "$(dirname "$0")/backend"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  . .venv/bin/activate
  python -m pip install --upgrade pip
  pip install -r requirements.txt
else
  . .venv/bin/activate
fi
echo
echo "Open http://localhost:8000 in your browser. Press Ctrl+C to stop."
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
