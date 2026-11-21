from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import quote, urlsplit
from uuid import UUID, uuid5

from app_paths import APP_NAME, APP_VERSION, INSTALL_MARKER

ROOT = Path(__file__).resolve().parents[1]
PUBLISHER = "Get it Simple"
PACKAGE_ID = "GetItSimple.ModManager"
MANIFEST_VERSION = "1.28.0"
UPGRADE_CODE = UUID("d1fa40ea-7779-4434-a975-d3a8a63c8ae3")
RELEASE_DIR = ROOT / "dist" / "release"
PORTABLE_EXE = ROOT / "dist" / "mod-manager-gui.exe"
PAYLOAD = ROOT / "dist" / "mod-manager-gui"


def installer_name(version: str) -> str:
    return f"mod-manager-{version}-x64.msi"


def archive_name(version: str) -> str:
    return f"mod-manager-{version}-winget.zip"


def msi_version(version: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version):
        raise ValueError(f"Invalid MSI version: {version!r}. Expected major.minor.patch.")
    major, minor, patch = map(int, version.split("."))
    if major > 255 or minor > 255 or patch > 65535:
        raise ValueError(f"MSI version component is out of range: {version}.")
    return major, minor, patch


def guid(value: UUID) -> str:
    return "{" + str(value).upper() + "}"


def previous_version() -> str:
    major, minor, patch = msi_version(APP_VERSION)
    if patch:
        return f"{major}.{minor}.{patch - 1}"
    if minor:
        return f"{major}.{minor - 1}.0"
    if major:
        return f"{major - 1}.0.0"
    raise ValueError("There is no older MSI version for the upgrade smoke test.")


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest().upper()


def package_metadata(path: Path) -> dict[str, str | int | None]:
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(ROOT / "tools" / "package_metadata.ps1"), str(path.resolve())],
        capture_output=True,
        encoding="utf-8",
    )
    if result.returncode:
        raise ValueError(f"Cannot read metadata for {path.name}:\n{result.stderr.strip()}")
    return json.loads(result.stdout)


def checked_msi(path: Path, version: str) -> dict[str, str]:
    msi_version(version)
    metadata = package_metadata(path)
    expected = {
        "ProductName": APP_NAME,
        "Manufacturer": PUBLISHER,
        "ProductVersion": version,
        "ProductCode": guid(uuid5(UPGRADE_CODE, version)),
        "UpgradeCode": guid(UPGRADE_CODE),
        "ALLUSERS": "1",
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise ValueError(f"{path.name}: expected MSI {key} {value!r}, found {metadata.get(key)!r}.")
    if metadata.get("MSIINSTALLPERUSER") or str(metadata.get("Template")).split(";")[0] != "x64":
        raise ValueError(f"{path.name}: expected a machine-only x64 MSI.")
    return expected


def build_msi(output: Path, wix: str, *, fixture: bool = False) -> Path:
    version = previous_version() if fixture else APP_VERSION
    msi_version(version)
    exe = PAYLOAD / PORTABLE_EXE.name
    runtime = PAYLOAD / "_internal"
    if not exe.is_file() or not runtime.is_dir():
        raise ValueError("Build the Windows onedir executable before packaging the MSI.")
    metadata = package_metadata(exe)
    if metadata.get("ProductVersion") != APP_VERSION or metadata.get("Machine") != 0x8664:
        raise ValueError(f"Rebuild the Windows x64 onedir executable for {APP_VERSION} before packaging.")
    output.mkdir(parents=True, exist_ok=True)
    path = output / installer_name(version)
    with tempfile.TemporaryDirectory(dir=output) as staging:
        staged = Path(staging) / path.name
        subprocess.run(
            [
                wix, "build", "-arch", "x64", "-o", str(staged),
                "-bindpath", f"Project={ROOT}",
                "-bindpath", f"Payload={PAYLOAD}",
                "-bindpath", f"Runtime={runtime}",
                "-d", f"AppName={APP_NAME}",
                "-d", f"AppVersion={version}",
                "-d", f"ProductCode={guid(uuid5(UPGRADE_CODE, version))}",
                "-d", f"UpgradeCode={guid(UPGRADE_CODE)}",
                "-d", f"InstallMarker={ROOT / 'installer' / INSTALL_MARKER}",
                str(ROOT / "installer" / "ModManager.wxs"),
            ],
            check=True,
        )
        checked_msi(staged, version)
        staged.replace(path)
    return path


def release_download_url(repository: str, tag: str, filename: str, server: str = "https://github.com") -> str:
    return f"{server.rstrip('/')}/{repository}/releases/download/{quote(tag, safe='')}/{quote(filename)}"


def manifest_files(metadata: dict[str, str], installer_url: str, checksum: str) -> dict[str, str]:
    url = urlsplit(installer_url)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.fragment:
        raise ValueError("InstallerUrl must be an HTTPS download URL.")
    if not re.fullmatch(r"[0-9A-F]{64}", checksum):
        raise ValueError("InstallerSha256 must be a SHA-256 hex digest.")
    version = metadata["ProductVersion"]
    identity = f"PackageIdentifier: {PACKAGE_ID}\nPackageVersion: {version}\n"
    entries = {
        "": ("version", "DefaultLocale: en-US\n"),
        ".installer": (
            "installer",
            "InstallerType: wix\n"
            "Scope: machine\n"
            "ElevationRequirement: elevationRequired\n"
            "UpgradeBehavior: install\n"
            "InstallModes:\n"
            "- silent\n"
            "- silentWithProgress\n"
            "Installers:\n"
            "- Architecture: x64\n"
            f"  InstallerUrl: {json.dumps(installer_url)}\n"
            f"  InstallerSha256: {checksum}\n"
            f"  ProductCode: '{metadata['ProductCode']}'\n"
            "  AppsAndFeaturesEntries:\n"
            f"  - DisplayName: {APP_NAME}\n"
            f"    Publisher: {PUBLISHER}\n"
            f"    DisplayVersion: {version}\n"
            f"    ProductCode: '{metadata['ProductCode']}'\n"
            f"    UpgradeCode: '{metadata['UpgradeCode']}'\n",
        ),
        ".locale.en-US": (
            "defaultLocale",
            f"PackageLocale: en-US\nPublisher: {PUBLISHER}\n"
            "PublisherUrl: https://github.com/get-it-simple\n"
            f"PackageName: {APP_NAME}\nLicense: MIT\nMoniker: mod-manager\n"
            "ShortDescription: Manage game mods using links or copies on Windows.\n",
        ),
        ".locale.uk-UA": (
            "locale",
            f"PackageLocale: uk-UA\nPublisher: {PUBLISHER}\n"
            f"PackageName: {APP_NAME}\nLicense: MIT\n"
            "ShortDescription: Керування ігровими модами за допомогою посилань або копій у Windows.\n",
        ),
    }
    return {
        f"{PACKAGE_ID}{suffix}.yaml": (
            f"# yaml-language-server: $schema=https://aka.ms/winget-manifest.{kind}.{MANIFEST_VERSION}.schema.json\n"
            f"{identity}{fields}ManifestType: {kind}\nManifestVersion: {MANIFEST_VERSION}\n"
        )
        for suffix, (kind, fields) in entries.items()
    }


def write_manifests(msi: Path, installer_url: str, output: Path) -> tuple[Path, Path]:
    version = APP_VERSION
    metadata = checked_msi(msi, version)
    manifests = manifest_files(metadata, installer_url, sha256(msi))
    relative_path = Path("manifests") / "g" / "GetItSimple" / "ModManager" / version
    directory = output / relative_path
    directory.mkdir(parents=True, exist_ok=True)
    archive = output / archive_name(version)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, content in manifests.items():
            data = content.replace("\n", "\r\n").encode("utf-8")
            (directory / name).write_bytes(data)
            info = zipfile.ZipInfo((relative_path / name).as_posix())
            bundle.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
    return directory, archive


def validate_manifests(directory: Path) -> None:
    subprocess.run(["winget", "--version"], check=True)
    subprocess.run(["winget", "validate", "--manifest", str(directory), "--disable-interactivity"], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the machine MSI or generate WinGet submission files.")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build-msi")
    build.add_argument("--wix", default="wix")
    build.add_argument("--output", type=Path, default=RELEASE_DIR)
    build.add_argument("--upgrade-fixture", action="store_true")
    manifests = commands.add_parser("winget")
    manifests.add_argument("--msi", required=True, type=Path)
    manifests.add_argument("--installer-url", required=True)
    manifests.add_argument("--output", type=Path, default=ROOT / "dist" / "winget")
    manifests.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    if args.command == "build-msi":
        if args.upgrade_fixture and args.output.resolve() == RELEASE_DIR:
            parser.error("The upgrade fixture requires a separate --output directory.")
        print(build_msi(args.output, args.wix, fixture=args.upgrade_fixture))
    else:
        directory, archive = write_manifests(args.msi, args.installer_url, args.output)
        if args.validate:
            validate_manifests(directory)
        print(archive)


if __name__ == "__main__":
    main()
