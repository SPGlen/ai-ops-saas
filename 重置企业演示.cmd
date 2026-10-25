@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\showcase.ps1" -Fresh
if errorlevel 1 pause
