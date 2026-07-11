@echo off
echo Setting up PDF Annotator...

echo Creating Python virtual environment...
python -m venv venv

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing requirements...
pip install -r requirements.txt

echo.
echo Setup complete! You can now run the application using "Run PDF Annotator.bat".
pause
