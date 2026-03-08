# PyInstaller spec file for SGAF Flask sidecar binary
# Build with: pyinstaller sgaf.spec

import os
import sys

block_cipher = None

# Ensure we're in the correct directory (src-python/)
spec_dir = SPECPATH
if not os.path.exists(os.path.join(spec_dir, "app", "__init__.py")):
    raise FileNotFoundError(f"Flask app not found in {spec_dir}/app — ensure PyInstaller runs from src-python/")

a = Analysis(
    [os.path.join(spec_dir, "app", "__init__.py")],
    pathex=[spec_dir],
    binaries=[],
    datas=[],
    hiddenimports=["flask", "bcrypt", "reportlab"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="sgaf-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
