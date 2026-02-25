#!/usr/bin/env python3
"""
Enclave Vault Build Script

Creates standalone executables and installers for macOS, Windows, and Linux.

Usage:
    python scripts/build.py                    # Build for current platform
    python scripts/build.py --platform macos   # Build for specific platform
    python scripts/build.py --all              # Build Python packages

Requirements:
    pip install pyinstaller flet[packaging]
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Project configuration
APP_NAME = "Enclave"
APP_VERSION = "0.1.0"
BUNDLE_ID = "ai.enclave.vault"
ENTRY_POINT = "advanced_vault/gui/vault_app.py"

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
ASSETS_DIR = PROJECT_ROOT / "assets"


def detect_platform() -> str:
    """Detect current platform."""
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    elif system == "windows":
        return "windows"
    else:
        return "linux"


def run_command(cmd: list, cwd: Path = None) -> bool:
    """Run a command and return success status."""
    print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or PROJECT_ROOT,
            check=True,
            capture_output=False
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}")
        return False
    except FileNotFoundError:
        print(f"Command not found: {cmd[0]}")
        return False


def clean_build():
    """Clean build artifacts."""
    print("Cleaning build artifacts...")
    for path in [DIST_DIR, BUILD_DIR]:
        if path.exists():
            shutil.rmtree(path)
    print("Clean complete.")


def build_with_flet(target_platform: str) -> bool:
    """Build using Flet's built-in packaging."""
    print(f"\nBuilding with Flet for {target_platform}...")

    cmd = [
        sys.executable, "-m", "flet", "pack",
        str(PROJECT_ROOT / ENTRY_POINT),
        "--name", APP_NAME,
        "--product-name", "Enclave Vault",
        "--product-version", APP_VERSION,
    ]

    # Platform-specific options
    if target_platform == "macos":
        cmd.extend(["--bundle-id", BUNDLE_ID])
        if (ASSETS_DIR / "icon.icns").exists():
            cmd.extend(["--icon", str(ASSETS_DIR / "icon.icns")])
    elif target_platform == "windows":
        if (ASSETS_DIR / "icon.ico").exists():
            cmd.extend(["--icon", str(ASSETS_DIR / "icon.ico")])

    # Add data files
    sep = ";" if target_platform == "windows" else ":"
    cmd.extend(["--add-data", f"advanced_vault{sep}advanced_vault"])

    return run_command(cmd)


def build_with_pyinstaller(target_platform: str) -> bool:
    """Build using PyInstaller for more control."""
    print(f"\nBuilding with PyInstaller for {target_platform}...")

    spec_file = PROJECT_ROOT / "enclave.spec"
    if not spec_file.exists():
        print(f"Error: {spec_file} not found")
        return False

    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(spec_file),
        "--clean",
        "--noconfirm",
    ]

    return run_command(cmd)


def create_dmg() -> bool:
    """Create macOS DMG installer."""
    print("\nCreating DMG installer...")

    app_path = DIST_DIR / f"{APP_NAME}.app"
    if not app_path.exists():
        print(f"Error: {app_path} not found. Run build first.")
        return False

    dmg_dir = DIST_DIR / "dmg"
    dmg_dir.mkdir(exist_ok=True)

    # Copy app to staging directory
    shutil.copytree(app_path, dmg_dir / f"{APP_NAME}.app", dirs_exist_ok=True)

    # Create Applications symlink
    apps_link = dmg_dir / "Applications"
    if not apps_link.exists():
        os.symlink("/Applications", apps_link)

    # Create DMG
    dmg_path = DIST_DIR / f"{APP_NAME}-{APP_VERSION}.dmg"
    cmd = [
        "hdiutil", "create",
        "-volname", APP_NAME,
        "-srcfolder", str(dmg_dir),
        "-ov", "-format", "UDZO",
        str(dmg_path)
    ]

    success = run_command(cmd)

    # Cleanup
    shutil.rmtree(dmg_dir)

    if success:
        print(f"Created: {dmg_path}")

    return success


def create_appimage() -> bool:
    """Create Linux AppImage."""
    print("\nCreating AppImage...")

    binary_path = DIST_DIR / APP_NAME
    if not binary_path.exists():
        print(f"Error: {binary_path} not found. Run build first.")
        return False

    appdir = DIST_DIR / "AppDir"
    appdir.mkdir(exist_ok=True)

    # Create directory structure
    (appdir / "usr" / "bin").mkdir(parents=True, exist_ok=True)
    (appdir / "usr" / "share" / "applications").mkdir(parents=True, exist_ok=True)
    (appdir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps").mkdir(parents=True, exist_ok=True)

    # Copy binary
    shutil.copy(binary_path, appdir / "usr" / "bin" / APP_NAME)

    # Create desktop file
    desktop_content = f"""[Desktop Entry]
Name=Enclave Vault
Comment=Privacy-first AI personal data manager
Exec={APP_NAME}
Icon={APP_NAME}
Type=Application
Categories=Utility;Security;
"""
    (appdir / f"{APP_NAME}.desktop").write_text(desktop_content)
    shutil.copy(appdir / f"{APP_NAME}.desktop", appdir / "usr" / "share" / "applications")

    # Copy icon if exists
    if (ASSETS_DIR / "icon.png").exists():
        shutil.copy(
            ASSETS_DIR / "icon.png",
            appdir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps" / f"{APP_NAME}.png"
        )

    # Create AppRun
    apprun = appdir / "AppRun"
    apprun.write_text(f"""#!/bin/bash
exec "$APPDIR/usr/bin/{APP_NAME}" "$@"
""")
    apprun.chmod(0o755)

    # Create AppImage
    appimage_path = DIST_DIR / f"{APP_NAME}-{APP_VERSION}.AppImage"

    # Check if appimagetool is available
    if shutil.which("appimagetool"):
        os.environ["ARCH"] = "x86_64"
        success = run_command(["appimagetool", str(appdir), str(appimage_path)])
    else:
        print("Warning: appimagetool not found. Install it for AppImage creation.")
        print("  wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage")
        print("  chmod +x appimagetool-x86_64.AppImage")
        print("  sudo mv appimagetool-x86_64.AppImage /usr/local/bin/appimagetool")
        success = False

    # Cleanup
    shutil.rmtree(appdir)

    return success


def build_python_packages() -> bool:
    """Build Python wheel and sdist packages."""
    print("\nBuilding Python packages...")

    cmd = [sys.executable, "-m", "build"]
    return run_command(cmd)


def main():
    parser = argparse.ArgumentParser(
        description="Build Enclave Vault executables and installers"
    )
    parser.add_argument(
        "--platform",
        choices=["macos", "windows", "linux"],
        default=detect_platform(),
        help="Target platform (default: auto-detect)"
    )
    parser.add_argument(
        "--method",
        choices=["flet", "pyinstaller"],
        default="flet",
        help="Build method (default: flet)"
    )
    parser.add_argument(
        "--installer",
        action="store_true",
        help="Also create installer (DMG/AppImage/MSI)"
    )
    parser.add_argument(
        "--python-packages",
        action="store_true",
        help="Build Python wheel and sdist"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean build artifacts before building"
    )

    args = parser.parse_args()

    if args.clean:
        clean_build()

    if args.python_packages:
        if not build_python_packages():
            sys.exit(1)
        return

    # Build executable
    if args.method == "flet":
        success = build_with_flet(args.platform)
    else:
        success = build_with_pyinstaller(args.platform)

    if not success:
        print("\nBuild failed!")
        sys.exit(1)

    print(f"\nBuild complete! Output in {DIST_DIR}/")

    # Create installer if requested
    if args.installer:
        if args.platform == "macos":
            create_dmg()
        elif args.platform == "linux":
            create_appimage()
        else:
            print("Note: Windows installer creation requires NSIS or WiX toolset")

    # Print output files
    print("\nCreated files:")
    for f in DIST_DIR.glob("*"):
        if f.is_file():
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"  {f.name} ({size_mb:.1f} MB)")
        elif f.is_dir() and f.suffix == ".app":
            print(f"  {f.name}/ (macOS app bundle)")


if __name__ == "__main__":
    main()
