from __future__ import annotations

import os
from pathlib import Path
from shutil import copyfile
from zipfile import ZipFile

import pytest

import app_paths
from mod_manager import storage
from tools import publish_release, release


@pytest.mark.skipif(os.name != "nt", reason="The machine installer is Windows-only")
def test_machine_data_is_per_user_and_portable_data_stays_next_to_exe(tmp_path, monkeypatch):
    program = tmp_path / "Program Files" / app_paths.APP_NAME
    program.mkdir(parents=True)
    assert app_paths.data_directory(program, frozen=True) == program
    (program / app_paths.INSTALL_MARKER).touch()
    assert app_paths.data_directory(program, frozen=False) == program

    def save_for_account(account: str, width: int) -> Path:
        user_dir = tmp_path / account
        monkeypatch.setenv("LOCALAPPDATA", str(user_dir))
        target = app_paths.data_directory(program, frozen=True) / "config.json"
        assert target == user_dir / app_paths.APP_NAME / "config.json"
        monkeypatch.setattr(storage, "CONFIG_PATH", target)
        storage.save_config({"window_width": width})
        assert storage.load_config()["window_width"] == width
        return target

    first = save_for_account("first", 800)
    second = save_for_account("second", 960)
    assert first.read_bytes() != second.read_bytes()
    assert not (program / "config.json").exists()


@pytest.fixture
def msi_metadata():
    return {
        "ProductName": app_paths.APP_NAME,
        "Manufacturer": release.PUBLISHER,
        "ProductVersion": app_paths.APP_VERSION,
        "ProductCode": release.guid(release.uuid5(release.UPGRADE_CODE, app_paths.APP_VERSION)),
        "UpgradeCode": release.guid(release.UPGRADE_CODE),
        "ALLUSERS": "1",
        "Template": "x64;1033",
    }


def test_winget_bundle_contains_matching_manifests(tmp_path, monkeypatch, msi_metadata):
    version = app_paths.APP_VERSION
    msi = tmp_path / release.installer_name(version)
    msi.write_bytes(b"synthetic installer bytes")
    monkeypatch.setattr(release, "package_metadata", lambda _: msi_metadata)
    url = release.release_download_url("publisher/repository", "release/example", msi.name)
    directory, bundle = release.write_manifests(msi, url, tmp_path)
    prefix = f"manifests/g/GetItSimple/ModManager/{version}"
    assert directory.relative_to(tmp_path).as_posix() == prefix
    types = {
        ".yaml": "version",
        ".installer.yaml": "installer",
        ".locale.en-US.yaml": "defaultLocale",
        ".locale.uk-UA.yaml": "locale",
    }
    filenames = {f"{release.PACKAGE_ID}{suffix}": kind for suffix, kind in types.items()}
    with ZipFile(bundle) as archive:
        assert set(archive.namelist()) == {f"{prefix}/{name}" for name in filenames}
        for name, kind in filenames.items():
            data = archive.read(f"{prefix}/{name}")
            assert data == (directory / name).read_bytes()
            assert not data.startswith(b"\xef\xbb\xbf")
            content = data.decode("utf-8")
            assert content.startswith(
                f"# yaml-language-server: $schema=https://aka.ms/winget-manifest.{kind}.1.28.0.schema.json\r\n"
            )
            assert f"\r\nPackageVersion: {version}\r\n" in content
            assert f"\r\nManifestType: {kind}\r\nManifestVersion: 1.28.0\r\n" in content
    content = (directory / f"{release.PACKAGE_ID}.installer.yaml").read_text(encoding="utf-8")
    assert f'InstallerUrl: "{url}"' in content
    assert f"InstallerSha256: {release.sha256(msi)}" in content
    assert "Scope: machine" in content
    assert "Architecture: x64" in content
    assert f"ProductCode: '{msi_metadata['ProductCode']}'" in content
    assert f"UpgradeCode: '{msi_metadata['UpgradeCode']}'" in content


@pytest.mark.parametrize(("key", "value"), [("ALLUSERS", "2"), ("Template", "Intel;1033"), ("ProductVersion", "1.0.0")])
def test_manifest_generation_rejects_a_mismatched_msi(tmp_path, monkeypatch, msi_metadata, key, value):
    monkeypatch.setattr(release, "package_metadata", lambda _: {**msi_metadata, key: value})
    with pytest.raises(ValueError):
        release.write_manifests(tmp_path / "installer.msi", "https://example.com/test.msi", tmp_path)
    assert not list(tmp_path.iterdir())


class FakeGitHub:
    repository = "publisher/repository"
    server = "https://github.com"
    commit = "a" * 40

    def __init__(self, assets_dir: Path):
        self.assets_dir = assets_dir
        self.assets_dir.mkdir()
        self.current = None
        self.published_commit = None
        self.uploads = []
        self.fail_upload = None

    def api(self, resource, *options, body=None):
        if resource == "releases?per_page=100":
            return [[self.current]] if self.current else []
        assert resource == "releases/1"
        self.current.update(body)
        if body.get("draft") is False:
            self.published_commit = self.current["target_commitish"]
        return self.current

    def tag_commit(self, _tag):
        return self.published_commit

    def release(self, action, tag, *arguments):
        if action == "create":
            self.current = {
                "id": 1, "draft": True, "tag_name": tag, "name": arguments[4],
                "target_commitish": self.commit, "assets": [],
            }
        else:
            assert action == "upload" and tag == self.current["tag_name"]
            file = Path(arguments[0])
            if self.fail_upload == file.suffix:
                self.current["assets"].append({"name": file.name, "state": "starter"})
                raise RuntimeError("upload interrupted")
            self.uploads.append(file.name)
            copyfile(file, self.assets_dir / file.name)
            self.current["assets"].append({
                "name": file.name, "state": "uploaded", "digest": f"sha256:{release.sha256(file).lower()}",
            })

    def download(self, asset, directory):
        path = directory / asset["name"]
        copyfile(self.assets_dir / asset["name"], path)
        return path

    def discard_failed_upload(self, asset):
        assert asset["state"] == "starter"
        self.current["assets"].remove(asset)


@pytest.mark.parametrize("existing_tag", [None, "release-1.2.43"])
def test_publication_recovers_interrupted_draft_and_preserves_published_installer(
    tmp_path, monkeypatch, msi_metadata, existing_tag
):
    binaries = tmp_path / "binaries"
    binaries.mkdir()
    version = app_paths.APP_VERSION
    installer = binaries / release.installer_name(version)
    installer.write_bytes(b"first MSI build")
    portable = binaries / f"mod-manager-gui-v{version}.exe"
    portable.write_bytes(b"portable build")
    manifests = tmp_path / "manifests"
    monkeypatch.setattr(release, "package_metadata", lambda _: msi_metadata)
    monkeypatch.setattr(publish_release, "RELEASE_DIR", binaries)
    monkeypatch.setattr(publish_release, "MANIFESTS_DIR", manifests)
    monkeypatch.setattr(publish_release, "validate_manifests", lambda path: None)
    monkeypatch.setattr(publish_release, "release_notes", lambda github, tag: "Built from the tested commit.")

    github = FakeGitHub(tmp_path / "github")
    if existing_tag:
        github.current = {
            "id": 1, "draft": True, "tag_name": existing_tag,
            "name": f"{app_paths.APP_NAME} v{version}", "target_commitish": "main", "assets": [],
        }
    github.fail_upload = ".exe"
    with pytest.raises(RuntimeError, match="upload interrupted"):
        publish_release.publish(github)
    assert github.current["draft"]
    assert github.current["target_commitish"] == github.commit
    assert github.published_commit is None
    first_hash = release.sha256(installer)

    installer.write_bytes(b"same commit was rebuilt with a new MSI timestamp")
    github.fail_upload = None
    publish_release.publish(github)
    assert not github.current["draft"]
    assert github.uploads == [installer.name, portable.name, release.archive_name(version)]
    assert release.sha256(github.assets_dir / installer.name) == first_hash
    with ZipFile(github.assets_dir / release.archive_name(version)) as bundle:
        installer_manifest = next(name for name in bundle.namelist() if name.endswith(".installer.yaml"))
        content = bundle.read(installer_manifest).decode("utf-8")
        tag = existing_tag or f"v{version}"
        assert first_hash in content
        assert f"/releases/download/{tag}/{installer.name}" in content

    publish_release.publish(github)
    assert len(github.uploads) == 3
    github.commit = "b" * 40
    with pytest.raises(ValueError, match="Bump APP_VERSION"):
        publish_release.publish(github)
    assert len(github.uploads) == 3
