@echo off
REM MangaStudio interactive console - double click me
chcp 65001 >nul
title MangaStudio
cd /d D:\MangaStudio
D:\LocalAI\ComfyUI\venv\Scripts\python.exe scripts\studio.py
pause
