@echo off
echo.
echo ========================================
echo  File Similarity Finder v2.0 Builder
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found! Please install Python first.
    echo Download from: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo ✅ Python found
echo.

REM Run the build script
echo 🚀 Starting build process...
echo.
python build.py

REM Check if build was successful
if exist "dist\FileSimilarityFinder.exe" (
    echo.
    echo ========================================
    echo  BUILD SUCCESSFUL!
    echo ========================================
    echo.
    echo Executable created: dist\FileSimilarityFinder.exe
    echo File size: 
    for %%A in ("dist\FileSimilarityFinder.exe") do echo    %%~zA bytes
    echo.
    echo Build complete! You can now distribute the executable.
) else (
    echo.
    echo ========================================
    echo  BUILD FAILED!
    echo ========================================
    echo.
    echo The executable was not created. Check the error messages above.
)

echo.
echo Press any key to exit...
pause >nul 