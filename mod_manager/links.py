from __future__ import annotations

from .i18n import t

import os
import shutil
import subprocess
from pathlib import Path
import tempfile
from typing import List, Tuple

from .platform_utils import is_junction, is_windows, supports_links

TARGET_EXISTS = t('target_already_exists')
SOURCE_MISSING = t('source_not_found')
UNSUPPORTED_LINKS = "unsupported_links"
UNSUPPORTED_LINK_MESSAGE = (
    t('the_destination_file_system_does_not_support_links_select_copy_as_the_ga')
)

def mklink(src: Path, dest: Path) -> Tuple[bool, str]:
    try:
        if dest.exists() or dest.is_symlink():
            return False, TARGET_EXISTS.format(dest)
        if not src.exists():
            return False, SOURCE_MISSING.format(src)
        if supports_links(dest.parent) is False:
            return False, UNSUPPORTED_LINK_MESSAGE

        if is_windows():
            if src.is_dir():
                cmd = ["cmd", "/c", "mklink", "/J", str(dest), str(src)]
            else:
                cmd = ["cmd", "/c", "mklink", str(dest), str(src)]
            res = subprocess.run(cmd, capture_output=True, text=True, creationflags=0x08000000)
            if res.returncode != 0:
                return False, res.stderr.strip() or res.stdout.strip() or t('mklink_error')
            return True, "OK"
        else:
            if src.is_dir():
                os.symlink(src, dest, target_is_directory=True)
            else:
                os.symlink(src, dest)
            return True, "OK"
    except Exception as e:
        return False, str(e)

def mklink_batch(items: List[Tuple[Path, Path, bool]]) -> List[Tuple[bool, str]]:
    results: List[Tuple[bool, str]] = [(False, t('mklink_error')) for _ in items]
    if not items:
        return results

    if not is_windows():
        for i, (src, dest, _is_dir) in enumerate(items):
            results[i] = mklink(src, dest)
        return results

    work_idxs: List[int] = []
    support: dict[Path, bool | None] = {}
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".bat", delete=False) as f:
        bat_path = f.name
        f.write("@echo off\n")
        for i, (src, dest, is_dir) in enumerate(items):
            if dest.exists() or dest.is_symlink():
                results[i] = (False, TARGET_EXISTS.format(dest))
                continue
            if not src.exists():
                results[i] = (False, SOURCE_MISSING.format(src))
                continue
            if dest.parent not in support:
                support[dest.parent] = supports_links(dest.parent)
            if support[dest.parent] is False:
                results[i] = (False, UNSUPPORTED_LINK_MESSAGE)
                continue

            work_idxs.append(i)
            f.write(f"echo __BEGIN__{i}__\n")
            if is_dir:
                f.write(f'mklink /J "{str(dest)}" "{str(src)}" 2>&1\n')
            else:
                f.write(f'mklink "{str(dest)}" "{str(src)}" 2>&1\n')
            f.write(f"echo __RC__{i}__%errorlevel%\n")
            f.write(f"echo __END__{i}__\n")

    try:
        if not work_idxs:
            return results
        res = subprocess.run(["cmd", "/d", "/q", "/c", bat_path], capture_output=True, text=True, creationflags=0x08000000)
        out = (res.stdout or "").splitlines()

        state: dict[int, dict] = {}
        current: int | None = None

        def _is_begin(line: str) -> int | None:
            s = line.strip()
            if s.startswith("__BEGIN__") and s.endswith("__"):
                mid = s[len("__BEGIN__") : -2]
                return int(mid) if mid.isdigit() else None
            return None

        def _is_rc(line: str) -> Tuple[int, int] | None:
            s = line.strip()
            if s.startswith("__RC__") and "__" in s[len("__RC__") :]:
                rest = s[len("__RC__") :]
                a, b = rest.split("__", 1)
                b2 = b.strip()
                if a.isdigit() and b2.isdigit():
                    return int(a), int(b2)
            return None

        def _is_end(line: str) -> int | None:
            s = line.strip()
            if s.startswith("__END__") and s.endswith("__"):
                mid = s[len("__END__") : -2]
                return int(mid) if mid.isdigit() else None
            return None

        for line in out:
            bi = _is_begin(line)
            if bi is not None:
                current = bi
                state[current] = {"lines": [], "rc": None}
                continue

            rci = _is_rc(line)
            if rci is not None:
                idx, rc = rci
                st = state.get(idx)
                if st is not None:
                    st["rc"] = rc
                continue

            ei = _is_end(line)
            if ei is not None:
                current = None
                continue

            if current is not None:
                state[current]["lines"].append(line)

        for i in work_idxs:
            st = state.get(i)
            if not st:
                results[i] = (False, (res.stderr or "").strip() or t('mklink_error'))
                continue
            rc = st.get("rc")
            msg = "\n".join((st.get("lines") or [])).strip()
            if rc == 0:
                results[i] = (True, "OK")
            else:
                results[i] = (False, msg or t('mklink_error'))

        return results
    except Exception as e:
        for i in work_idxs:
            results[i] = (False, str(e))
        return results
    finally:
        try:
            os.remove(bat_path)
        except Exception:
            pass

def unlink_path(path: Path) -> Tuple[bool, str]:
    try:
        junction = is_junction(path)
        if not path.exists() and not path.is_symlink() and not junction:
            return False, t('already_removed')
        if junction:
            os.rmdir(path)
        elif path.is_dir() and not path.is_symlink():
            try:
                os.rmdir(path)
            except OSError:
                return False, t('not_a_link_or_not_empty')
        else:
            path.unlink()
        return True, "OK"
    except Exception as e:
        return False, str(e)

def unlink_broken_link(path: Path) -> Tuple[bool, str]:
    try:
        if not (path.is_symlink() or is_junction(path)) or path.exists():
            return False, t('not_a_broken_link_left_unchanged')
        return unlink_path(path)
    except OSError as error:
        return False, str(error)


def copy_path(src: Path, dest: Path, overwrite: bool = False) -> Tuple[bool, str]:
    try:
        if not src.exists():
            return False, SOURCE_MISSING.format(src)
        if dest.exists() or dest.is_symlink():
            if not overwrite:
                return False, TARGET_EXISTS.format(dest)
            ok, msg = remove_path(dest)
            if not ok:
                return False, msg
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
        return True, "OK"
    except Exception as e:
        return False, str(e)

def copy_batch(items: List[Tuple[Path, Path, bool]], overwrite: bool = False) -> List[Tuple[bool, str]]:
    return [copy_path(src, dest, overwrite) for src, dest, _is_dir in items]

def remove_path(path: Path) -> Tuple[bool, str]:
    """Remove a link or a copy installed in the game mods folder."""
    try:
        if path.is_symlink() or is_junction(path):
            return unlink_path(path)
        if not path.exists():
            return False, t('already_removed')
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        return True, "OK"
    except Exception as e:
        return False, str(e)
