@echo off
REM Re-compose pages after editing dialogue in storyboards\<slug>.json
REM   compose.bat <slug>            e.g. compose.bat raiden_ep01
cd /d D:\MangaStudio
if "%~1"=="" ( echo Usage: compose.bat slug & pause & exit /b 1 )
D:\LocalAI\ComfyUI\venv\Scripts\python.exe scripts\compose_pages.py storyboards\%1.json
pause
