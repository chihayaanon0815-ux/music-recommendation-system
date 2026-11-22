@echo off
cd /d "%~dp0.."
python -m pip install -r packaging\requirements.txt
if errorlevel 1 exit /b 1
python -m PyInstaller --noconfirm --clean --onedir --name MusicRecommendation-TEST --paths . --add-data "web\templates;web\templates" --add-data "web\static;web\static" --collect-submodules recommender packaging\launcher.py
if errorlevel 1 exit /b 1
echo TEST BUILD ONLY. Copy data\processed alongside the executable as documented.
