@echo off
setlocal
cd /d "%~dp0"
title OLV Watch-Along setup
echo.
echo   OLV Watch-Along setup
echo   Connects this folder to your Open-LLM-VTuber. Close Open-LLM-VTuber first.
echo.
set "OLV="
set /p "OLV=Open-LLM-VTuber folder (drag the folder into this window, then press Enter): "
if not defined OLV goto nofolder
set "OLV=%OLV:"=%"
if not exist "%OLV%\.venv\Scripts\python.exe" goto nopython
echo.
"%OLV%\.venv\Scripts\python.exe" -I tools\setup.py "%OLV%" %*
echo.
pause
exit /b

:nofolder
echo No folder given.
pause
exit /b 1

:nopython
echo.
echo Could not find "%OLV%\.venv\Scripts\python.exe".
echo Pick the main Open-LLM-VTuber folder (the one with conf.yaml in it).
echo If you installed Open-LLM-VTuber without uv, see "Manual setup" in the README.
pause
exit /b 1
