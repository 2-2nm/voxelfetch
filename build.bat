@echo off
setlocal
cd /d "%~dp0"

python -m pip install --upgrade pyinstaller || goto :fail

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

python -m PyInstaller --noconfirm --onedir --name voxelfetch --distpath build\app --workpath build\work --specpath build\spec --paths "%~dp0voxelfetch" voxelfetch\__main__.py || goto :fail

mkdir build\payload
xcopy /e /i /y build\app\voxelfetch build\payload >nul
copy /y voxelfetch\default.vxl build\payload >nul
copy /y voxelfetch\config.json build\payload >nul
copy /y voxelfetch\CONFIG.md build\payload >nul
xcopy /e /i /y voxelfetch\vxl build\payload\vxl >nul

python -m PyInstaller --noconfirm --onefile --name voxelfetch-setup --distpath dist --workpath build\work2 --specpath build\spec2 --add-data "%~dp0build\payload;payload" installer.py || goto :fail

echo Built dist\voxelfetch-setup.exe
pause
exit /b 0

:fail
echo Build failed.
pause
exit /b 1