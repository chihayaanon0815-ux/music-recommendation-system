@echo off
cd /d "%~dp0.."
python -m pip install -r packaging\requirements.txt
if errorlevel 1 exit /b 1
python -m PyInstaller --noconfirm --clean --onedir --name MusicRecommendation-Playlists --paths . --add-data "web\templates;web\templates" --add-data "web\static;web\static" --add-data "data_processing\genre_map_zh.csv;data_processing" --collect-submodules recommender packaging\launcher.py
if errorlevel 1 exit /b 1
echo Build complete. Copy data\processed alongside the executable as documented.
