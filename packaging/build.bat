@echo off
cd /d "%~dp0.."
python -m pip install -r packaging\requirements.txt
if errorlevel 1 exit /b 1
python -m PyInstaller --noconfirm --clean --onedir --name MusicRecommendation --paths . --add-data "web\templates;web\templates" --add-data "web\static;web\static" --hidden-import recommender.recommend packaging\launcher.py
if errorlevel 1 exit /b 1
echo Build complete. Copy data\processed alongside the executable as documented.
