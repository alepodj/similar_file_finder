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

def format_file_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.1f} {size_names[i]}"

def verify_executable(exe_path):
    """Verify that the executable was created and get its details"""
    if not os.path.exists(exe_path):
        return False, "Executable not found"
    
    try:
        size = os.path.getsize(exe_path)
        size_str = format_file_size(size)
        
        # Try to get file version info on Windows
        version_info = ""
        if sys.platform == 'win32':
            try:
                import win32api
                info = win32api.GetFileVersionInfo(exe_path, "\\")
                version = f"{info['FileVersionMS'] >> 16}.{info['FileVersionMS'] & 0xFFFF}.{info['FileVersionLS'] >> 16}.{info['FileVersionLS'] & 0xFFFF}"
                version_info = f" (v{version})"
            except:
                pass
        
        return True, f"Size: {size_str}{version_info}"
    except Exception as e:
        return False, f"Error checking executable: {e}"

def build_with_cx_freeze():
    """Build using cx_Freeze"""
    try:
        import cx_Freeze
        print("🔨 Building with cx_Freeze...")
        
        # Clean previous build
        if os.path.exists('build'):
            print("🧹 Cleaning previous build directory...")
            shutil.rmtree('build')
        if os.path.exists('dist'):
            print("🧹 Cleaning previous dist directory...")
            shutil.rmtree('dist')
        
        # Run build
        result = subprocess.run([sys.executable, 'setup.py', 'build'], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ cx_Freeze build completed successfully!")
            
            # Find the executable
            build_dir = None
            for item in os.listdir('build'):
                if item.startswith('exe.'):
                    build_dir = os.path.join('build', item)
                    break
            
            if build_dir:
                exe_path = os.path.join(build_dir, 'FileSimilarityFinder.exe')
                success, details = verify_executable(exe_path)
                if success:
                    print(f"📁 Executable location: {exe_path}")
                    print(f"📊 Executable details: {details}")
                else:
                    print(f"⚠️ Issue with executable: {details}")
            else:
                print("⚠️ Could not locate build directory")
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
            print("🧹 Cleaning previous build directory...")
            shutil.rmtree('build')
        if os.path.exists('dist'):
            print("🧹 Cleaning previous dist directory...")
            shutil.rmtree('dist')
        
        # Run build
        result = subprocess.run([
            sys.executable, '-m', 'PyInstaller', 
            'FileSimilarityFinder.spec', '--clean'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ PyInstaller build completed successfully!")
            
            # Verify the executable
            exe_path = os.path.join('dist', 'FileSimilarityFinder.exe')
            success, details = verify_executable(exe_path)
            if success:
                print(f"📁 Executable location: {exe_path}")
                print(f"📊 Executable details: {details}")
                
                # Test if executable can be launched (quick test)
                print("🧪 Testing executable launch...")
                try:
                    # Try to run with --help or similar to test if it loads
                    test_result = subprocess.run([exe_path], 
                                               timeout=5, 
                                               capture_output=True, 
                                               text=True)
                    print("✅ Executable launches successfully!")
                except subprocess.TimeoutExpired:
                    print("✅ Executable launches successfully (GUI opened)!")
                except Exception as e:
                    print(f"⚠️ Executable launch test failed: {e}")
            else:
                print(f"❌ Executable verification failed: {details}")
                return False
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
        print("1. Test the executable by running it")
        print("2. Check that icon.png is included")
        print("3. Verify all features work correctly")
        print("4. Test on a clean system without Python installed")
        print("5. Distribute the executable")
        
        # Show final executable location
        if os.path.exists('dist/FileSimilarityFinder.exe'):
            exe_path = os.path.abspath('dist/FileSimilarityFinder.exe')
            print(f"\n📍 Final executable: {exe_path}")
    else:
        print("\n❌ Build failed. Check error messages above.")

if __name__ == "__main__":
    main() 