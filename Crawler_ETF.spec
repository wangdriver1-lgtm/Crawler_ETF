# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import ssl

# Some bundled Python runtimes load this certificate file beside ssl.py.
# Preserve that TLS configuration in the frozen application as well.
ssl_support_file = Path(ssl.__file__).with_name('codex-rejected-cas.pem')
ssl_support_data = [(str(ssl_support_file), '.')] if ssl_support_file.is_file() else []

a = Analysis(
    ['Crawler_ETF.py'],
    pathex=[],
    binaries=[],
    datas=ssl_support_data,
    # Selenium resolves Chrome's driver lazily; PyInstaller cannot infer it.
    hiddenimports=['selenium.webdriver.chrome.webdriver'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Crawler_ETF',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
