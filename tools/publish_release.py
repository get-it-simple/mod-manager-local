from __future__ import annotations

import json
import os
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from app_paths import APP_NAME, APP_VERSION
from tools.release import (
    RELEASE_DIR,
    ROOT,
    archive_name,
    installer_name,
    release_download_url,
    sha256,
    validate_manifests,
    write_manifests,
)

MANIFESTS_DIR = ROOT / "dist" / "winget"


@dataclass(frozen=True)
class GitHub:
    repository: str
    server: str
    commit: str

    def api(self, resource: str, *options: str, body: dict | None = None):
        command = ["gh", "api", f"repos/{self.repository}/{resource}", *options]
        if body is not None:
            command.extend(["--method", "PATCH", "--input", "-"])
        response = subprocess.check_output(command, input=json.dumps(body) if body is not None else None, encoding="utf-8")
        return json.loads(response)

    def tag_commit(self, tag: str) -> str | None:
        refs = self.api(f"git/matching-refs/tags/{quote(tag, safe='/')}")
        target = next((ref["object"] for ref in refs if ref["ref"] == f"refs/tags/{tag}"), None)
        while target and target["type"] == "tag":
            target = self.api(f"git/tags/{target['sha']}")["object"]
        if target and target["type"] != "commit":
            raise ValueError(f"Tag {tag} does not target a commit.")
        return target["sha"] if target else None

    def release(self, *arguments: str) -> None:
        subprocess.run(["gh", "release", *arguments, "--repo", self.repository], check=True)

    def download(self, asset: dict, directory: Path) -> Path:
        path = directory / asset["name"]
        with path.open("wb") as target:
            subprocess.run(
                ["gh", "api", f"repos/{self.repository}/releases/assets/{asset['id']}",
                 "-H", "Accept: application/octet-stream"],
                stdout=target,
                check=True,
            )
        digest = asset.get("digest")
        if digest and digest.lower() != f"sha256:{sha256(path).lower()}":
            raise ValueError(f"GitHub asset digest does not match {path.name}.")
        return path

    def discard_failed_upload(self, asset: dict) -> None:
        subprocess.run(
            ["gh", "api", "--method", "DELETE", f"repos/{self.repository}/releases/assets/{asset['id']}"],
            check=True,
        )


def select_release(pages: list[list[dict]], tag: str, title: str) -> dict | None:
    matches = [
        release for page in pages for release in page
        if release["tag_name"] == tag or release.get("name") == title
    ]
    if len(matches) > 1:
        raise ValueError(f"More than one GitHub release matches {title}.")
    return matches[0] if matches else None


def check_release_target(
    release: dict | None, tagged_commit: str | None, commit: str, managed_assets: set[str]
) -> None:
    if tagged_commit is not None:
        if tagged_commit != commit:
            raise ValueError(f"This version is already tagged at {tagged_commit}. Bump APP_VERSION to publish {commit}.")
        return
    if release and (
        not release["draft"] or (
            managed_assets.intersection(asset["name"] for asset in release["assets"])
            and release["target_commitish"] != commit
        )
    ):
        raise ValueError("The existing release does not identify the checked-out commit.")


def release_notes(github: GitHub, tag: str) -> str:
    version_tag = f"v{APP_VERSION}"
    tags = subprocess.check_output(
        ["git", "tag", "--list", "v*", "--merged", "HEAD", "--sort=-creatordate"], encoding="utf-8",
    ).splitlines()
    previous = next((
        item for item in tags if item not in {tag, version_tag} and not item.startswith(version_tag + "-")
    ), None)
    range_spec = f"{previous}..HEAD" if previous else "HEAD"
    history = subprocess.check_output(
        ["git", "log", range_spec, "--no-merges", "--format=%H%x09%h%x09%s"], encoding="utf-8",
    ).splitlines()
    base = f"{github.server}/{github.repository}"
    lines = [f"Built from [`{github.commit}`]({base}/commit/{github.commit}).", "", "## Commits", ""]
    for line in history:
        commit, short_commit, title = line.split("\t", 2)
        lines.append(f"- [`{short_commit}`]({base}/commit/{commit}) {title}")
    if previous:
        lines.extend(["", f"Previous release: [{previous}]({base}/releases/tag/{quote(previous, safe='')})"])
    return "\n".join(lines) + "\n"


def zip_contents(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as bundle:
        names = bundle.namelist()
        if len(set(names)) != len(names):
            raise ValueError(f"Duplicate entries in {path.name}.")
        return {name: bundle.read(name) for name in names}


def publish(github: GitHub) -> None:
    version = APP_VERSION
    version_tag = f"v{version}"
    title = f"{APP_NAME} {version_tag}"
    msi_name = installer_name(version)
    winget_name = archive_name(version)
    portable_name = f"mod-manager-gui-{version_tag}.exe"
    managed = {msi_name, winget_name, portable_name}

    pages = github.api("releases?per_page=100", "--paginate", "--slurp")
    release = select_release(pages, version_tag, title)
    tag = release["tag_name"] if release else version_tag
    tagged_commit = github.tag_commit(tag)
    check_release_target(release, tagged_commit, github.commit, managed)
    assets = {asset["name"]: asset for asset in release["assets"] if asset["state"] == "uploaded"} if release else {}
    failed_uploads = [
        asset for asset in release["assets"] if asset["name"] in managed and asset["state"] != "uploaded"
    ] if release else []
    missing = managed - assets.keys()
    if release and release.get("immutable") and missing:
        raise ValueError(f"The immutable release is missing: {', '.join(sorted(missing))}.")
    if any(asset["state"] != "starter" for asset in failed_uploads):
        raise ValueError("GitHub has a managed asset in an unexpected state.")
    if winget_name in assets and msi_name not in assets:
        raise ValueError("The release has a WinGet bundle but its corresponding MSI is missing.")

    with tempfile.TemporaryDirectory(dir=RELEASE_DIR) as temporary:
        staging = Path(temporary)
        msi = github.download(assets[msi_name], staging) if msi_name in assets else RELEASE_DIR / msi_name
        url = release_download_url(github.repository, tag, msi_name, github.server)
        directory, archive = write_manifests(msi, url, MANIFESTS_DIR)
        validate_manifests(directory)
        if winget_name in assets:
            current_bundle = github.download(assets[winget_name], staging)
            if zip_contents(current_bundle) != zip_contents(archive):
                raise ValueError("The existing WinGet bundle differs from the published MSI or manifest metadata.")
        if release and not release["draft"] and not missing:
            print(f"{tag} already has a verified MSI and WinGet bundle.")
            return
        files = {msi_name: msi, winget_name: archive, portable_name: RELEASE_DIR / portable_name}
        for name in missing:
            if not files[name].is_file():
                raise ValueError(f"Missing build artifact: {files[name]}")
        notes = release_notes(github, tag)
        if release is None:
            notes_path = staging / "release-notes.md"
            notes_path.write_text(notes, encoding="utf-8")
            github.release("create", tag, "--draft", "--target", github.commit, "--title", title,
                           "--notes-file", str(notes_path))
        elif release["draft"] and tagged_commit is None and release["target_commitish"] != github.commit:
            github.api(f"releases/{release['id']}", body={"target_commitish": github.commit})
        for asset in failed_uploads:
            github.discard_failed_upload(asset)
        for name in (msi_name, portable_name, winget_name):
            if name in missing:
                github.release("upload", tag, str(files[name]))
        pages = github.api("releases?per_page=100", "--paginate", "--slurp")
        updated = select_release(pages, version_tag, title)
        if updated is None or updated["tag_name"] != tag:
            raise ValueError("The GitHub release changed during upload.")
        check_release_target(updated, github.tag_commit(tag), github.commit, managed)
        uploaded = {asset["name"]: asset for asset in updated["assets"] if asset["state"] == "uploaded"}
        for name in missing:
            asset = uploaded.get(name)
            if asset is None:
                raise ValueError(f"GitHub did not complete the upload of {name}.")
            digest = asset.get("digest")
            verified = digest.lower() == f"sha256:{sha256(files[name]).lower()}" if digest else (
                sha256(github.download(asset, staging)) == sha256(files[name])
            )
            if not verified:
                raise ValueError(f"GitHub did not return the expected SHA-256 for {name}.")
        body = {"draft": False, "body": notes, "target_commitish": github.commit}
        github.api(f"releases/{updated['id']}", body=body)
        if github.tag_commit(tag) != github.commit:
            raise ValueError(f"The published tag {tag} does not match the checked-out commit.")


if __name__ == "__main__":
    publish(GitHub(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_SERVER_URL"], os.environ["GITHUB_SHA"]))
