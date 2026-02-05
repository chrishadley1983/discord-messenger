@echo off
cd /d "%~dp0"
echo Stopping Peter Dashboard...
python -c "from service_manager import stop_service; r=stop_service('peter_dashboard', force_cleanup=True); print('Stopped' if r['success'] else 'Failed')"
echo Done.
timeout /t 2 >nul
