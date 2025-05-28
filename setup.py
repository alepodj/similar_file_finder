import sys
import os

try:
    from cx_Freeze import setup, Executable
except ImportError:
    print("cx_Freeze not installed. Install with: pip install cx_Freeze")
    print("Or use the build script: python build.py")
    sys.exit(1)

# Dependencies are automatically detected, but it might need fine tuning.
build_options = {
    'packages': [
        'tkinter', 'fuzzywuzzy', 'difflib', 'hashlib', 'pathlib', 'threading', 
        'os', 'time', 'multiprocessing', 'concurrent.futures', 'itertools',
        'functools', 'json', 'csv', 'datetime', 'collections', 'typing',
        'sv_ttk', 'PIL', 'xxhash'
    ],
    'excludes': [
        'test', 'unittest', 'pdb', 'doctest', 'argparse'
    ],
    'include_files': [
        ('icon.png', 'icon.png'),  # Include the application icon
        ('README.md', 'README.md'),  # Include documentation
        ('requirements.txt', 'requirements.txt')  # Include requirements
    ],
    'zip_include_packages': ['*'],
    'zip_exclude_packages': []
}

# Windows-specific base for GUI application
base = 'Win32GUI' if sys.platform == 'win32' else None

executables = [
    Executable(
        'gui_app.py', 
        base=base, 
        target_name='FileSimilarityFinder.exe',
        icon='icon.png' if os.path.exists('icon.png') else None,
        copyright='File Similarity Finder v2.0'
    )
]

setup(
    name='File Similarity Finder',
    version='2.0',
    description='High-performance file similarity finder with multiprocessing, xxHash support, and modern GUI',
    author='File Similarity Finder Team',
    options={'build_exe': build_options},
    executables=executables
) 