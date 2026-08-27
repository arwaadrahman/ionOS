# PyInstaller one-file sidecar prototype for the approved ARM64 Phase 0C proof.
# Generated output is copied to Tauri's target-triple sidecar path by build-sidecar.sh.
a = Analysis(
    ["../ion_api/__main__.py"],
    pathex=[".."],
    binaries=[],
    datas=[],
    hiddenimports=[],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ion-api",
    console=True,
    target_arch="arm64",
)
