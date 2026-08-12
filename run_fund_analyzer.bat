@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Setup required. Follow README.md to create the local environment.
  pause
  exit /b 1
)
if not exist ".streamlit\secrets.toml" (
  echo AI configuration is optional but not configured.
  echo Copy .streamlit\secrets.toml.example to secrets.toml to enable MiniMax analysis.
)
".venv\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1

