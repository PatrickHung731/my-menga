@echo off
REM MangaStudio one-click: drag a story .txt onto this file, or:
REM   manga.bat stories\ep1.txt --series raiden --title-zh NAME --style yuyu_hakusho --pages 8
cd /d D:\MangaStudio
D:\LocalAI\ComfyUI\venv\Scripts\python.exe scripts\story2manga.py %*
pause
