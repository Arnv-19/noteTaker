@echo off
echo ============================================
echo   PDF Annotator - Setup
echo ============================================
echo.

if not exist "venv\" (
    echo Creating Python virtual environment...
    python -m venv venv
) else (
    echo Virtual environment already exists - reusing it.
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Upgrading pip...
python -m pip install --upgrade pip

echo Installing / updating requirements...
echo (First run downloads PyQt6-WebEngine, which is large - this may take a few minutes.)
pip install -r requirements.txt

echo.
echo ============================================
echo   Setup complete!
echo   Run the app with "Run PDF Annotator.bat".
echo   Re-run this setup any time you update the
echo   project to pull in new dependencies.
echo ============================================
pause
