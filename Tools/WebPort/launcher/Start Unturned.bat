@echo off
title Unturned (web port) - close this window to stop
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python is needed: install it from https://www.python.org/downloads/ and run this again.
  pause
  exit /b 1
)
python launch.py
if errorlevel 1 pause
