@echo off
cd /d "%~dp0"
echo Starting Streamlit...
echo Open in browser: http://localhost:8501
echo Or try: http://127.0.0.1:8501
echo.
python -m streamlit run app.py --server.port 8501
pause
