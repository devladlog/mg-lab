@echo off
rem Double-click this file. Windows asks for administrator approval (UAC), then builds the MG Lab.
rem Safe to run again: finished stages are skipped. After the first run enables Hyper-V, restart and run it again.
powershell.exe -NoProfile -Command "Start-Process powershell.exe -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-NoExit','-File','\"%~dp0Start-MGLab.ps1\"'"
