#!/usr/bin/env python3
"""
Build script for File Similarity Finder
Supports both cx_Freeze and PyInstaller
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def check_requirements():
    """Check if all required packages are installed"""
    # Map pip package names to import names
    package_imports = {
        'fuzzywuzzy': 'fuzzywuzzy',
        'python-Levenshtein': 'Levenshtein', 
        'sv-ttk': 'sv_ttk',
        'Pillow': 'PIL',
        'xxhash': 'xxhash'
    }
    
    missing = []
    for pip_name, import_name in package_imports.items():
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pip_name)
    
    if missing:
        print(f"❌ Missing required packages: {', '.join(missing)}")
        print("Install with: pip install " + " ".join(missing))
        return False
    
    print("✅ All required packages are installed")
    return True

def build_with_cx_freeze():
    """Build using cx_Freeze"""
    try:
        import cx_Freeze
        print("🔨 Building with cx_Freeze...")
        
        # Clean previous build
        if os.path.exists('build'):
            shutil.rmtree('build')
        if os.path.exists('dist'):
            shutil.rmtree('dist')
        
        # Run build
        result = subprocess.run([sys.executable, 'setup.py', 'build'], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ cx_Freeze build completed successfully!")
            print("📁 Executable location: build/exe.win-amd64-*/")
            return True
        else:
            print(f"❌ cx_Freeze build failed: {result.stderr}")
            return False
            
    except ImportError:
        print("❌ cx_Freeze not installed. Install with: pip install cx_Freeze")
        return False

def build_with_pyinstaller():
    """Build using PyInstaller"""
    try:
        import importlib
        importlib.import_module('PyInstaller')
        print("🔨 Building with PyInstaller...")
        
        # Clean previous build
        if os.path.exists('build'):
            shutil.rmtree('build')
        if os.path.exists('dist'):
            shutil.rmtree('dist')
        
        # Run build
        result = subprocess.run([
            sys.executable, '-m', 'PyInstaller', 
            'FileSimilarityFinder.spec', '--clean'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ PyInstaller build completed successfully!")
            print("📁 Executable location: dist/FileSimilarityFinder.exe")
            return True
        else:
            print(f"❌ PyInstaller build failed: {result.stderr}")
            return False
            
    except ImportError:
        print("❌ PyInstaller not installed. Install with: pip install pyinstaller")
        return False

def main():
    """Main build function"""
    print("🚀 File Similarity Finder v2.0 - Build Script")
    print("=" * 50)
    
    # Check if we're in the right directory
    if not os.path.exists('gui_app.py'):
        print("❌ gui_app.py not found. Run this script from the project directory.")
        return
    
    # Check requirements
    if not check_requirements():
        return
    
    # Ask user which build tool to use
    print("\nChoose build tool:")
    print("1. PyInstaller (recommended)")
    print("2. cx_Freeze")
    print("3. Both")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    success = False
    
    if choice == "1":
        success = build_with_pyinstaller()
    elif choice == "2":
        success = build_with_cx_freeze()
    elif choice == "3":
        print("\n" + "="*30)
        success1 = build_with_pyinstaller()
        print("\n" + "="*30)
        success2 = build_with_cx_freeze()
        success = success1 or success2
    else:
        print("❌ Invalid choice")
        return
    
    if success:
        print("\n🎉 Build completed successfully!")
        print("\n📋 Next steps:")
        print("1. Test the executable")
        print("2. Check that icon.png is included")
        print("3. Verify all features work correctly")
        print("4. Distribute the executable")
    else:
        print("\n❌ Build failed. Check error messages above.")

if __name__ == "__main__":
    main() 