@echo off
REM Redo one panel: redo.bat <slug> <page:panel>   e.g. redo.bat raiden_ep01 1:3
cd /d D:\MangaStudio
if "%~2"=="" ( echo Usage: redo.bat slug page:panel & pause & exit /b 1 )
D:\LocalAI\ComfyUI\venv\Scripts\python.exe scripts\generate_panels.py storyboards\%1.json --only %2 --redo
D:\LocalAI\ComfyUI\venv\Scripts\python.exe scripts\compose_pages.py storyboards\%1.json
pause
