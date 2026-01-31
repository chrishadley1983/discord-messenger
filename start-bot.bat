@echo off
REM Discord-Messenger Bot Startup Script

cd /d "C:\Users\Chris Hadley\Discord-Messenger"

REM Activate virtual environment if exists
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM Use Python launcher script for single-instance check
python start_single.py
