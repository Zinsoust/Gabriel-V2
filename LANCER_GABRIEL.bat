@echo off
title Gabriel - Intelligence Humaine Avancee
echo.
echo  ██████╗  █████╗ ██████╗ ██████╗ ██╗███████╗██╗
echo  ██╔════╝ ██╔══██╗██╔══██╗██╔══██╗██║██╔════╝██║
echo  ██║  ███╗███████║██████╔╝██████╔╝██║█████╗  ██║
echo  ██║   ██║██╔══██║██╔══██╗██╔══██╗██║██╔══╝  ██║
echo  ╚██████╔╝██║  ██║██████╔╝██║  ██║██║███████╗███████╗
echo   ╚═════╝ ╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝╚═╝╚══════╝╚══════╝
echo.
echo  Intelligence Humaine Avancee
echo  ================================
echo.

cd /d "%~dp0"

echo [1/3] Verification de Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERREUR: Python n'est pas installe.
    echo Telechargez Python sur https://python.org
    echo Cochez "Add Python to PATH" lors de l'installation.
    pause
    exit
)
echo       Python OK

echo [2/3] Installation des dependances...
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ERREUR lors de l'installation des dependances.
    pause
    exit
)
echo       Dependances OK

echo [3/3] Demarrage de Gabriel...
echo.
echo  Ouvrez votre navigateur sur : http://localhost:5050
echo  Appuyez sur Ctrl+C pour arreter Gabriel.
echo.
start "" "http://localhost:5050"
python app.py
pause
