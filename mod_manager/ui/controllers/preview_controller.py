from __future__ import annotations

from ...i18n import t

from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Callable

from PySide6 import QtGui

from ...dragdrop import read_clipboard_paths
from ...log import logger
from ...mods import IMAGE_EXTENSIONS, import_mod_images, is_image_file
from ..image_clipboard import read_clipboard_image
from ..dialogs import prompts


@dataclass
class PreviewSource:
    path: Path
    release: Callable | None = None

    def close(self) -> None:
        release, self.release = self.release, None
        if release:
            try:
                release()
            except OSError as exc:
                logger.warning(t('cannot_release_temporary_preview_s'), exc)


def read_preview_image(path: Path) -> QtGui.QImage:
    reader = QtGui.QImageReader(str(path))
    reader.setAutoTransform(True)
    return reader.read()


class PreviewController:
    def __init__(self, window):
        self.window = window

    def paste_paths(self, paths) -> None:
        source = PreviewSource(Path(paths[0]), getattr(paths, "close", None))
        if len(paths) != 1:
            try:
                prompts.show_warning(self.window, t('text_1e63fa10de76'), t('paste_one_image_at_a_time'))
            finally:
                source.close()
            return
        self.apply(source)

    def paste_image(self, path: Path) -> None:
        self.apply(PreviewSource(path, lambda: path.unlink(missing_ok=True)))

    def _clipboard_source(self) -> PreviewSource | None:
        paths = read_clipboard_paths()
        if paths:
            if len(paths) == 1 and is_image_file(paths[0]):
                return PreviewSource(Path(paths[0]), getattr(paths, "close", None))
            release = getattr(paths, "close", None)
            if release:
                release()
            return None
        path = read_clipboard_image()
        return PreviewSource(path, lambda: path.unlink(missing_ok=True)) if path else None

    def choose(self) -> None:
        names = self.window._selected_mod_names()
        if not names or self.window.busy:
            return
        try:
            source = self._clipboard_source()
        except OSError as exc:
            prompts.show_error(self.window, t('text_1e63fa10de76'), t('cannot_assign_preview_value0', value0=str(exc)))
            return
        if source:
            choice = "cancel"
            try:
                if not read_preview_image(source.path).isNull():
                    choice = prompts.choose_preview_image(self.window, source.path, len(names), clipboard=True)
                else:
                    choice = "file"
            finally:
                if choice != "apply":
                    source.close()
            if choice == "apply":
                self.apply(source, names, confirmed=True)
                return
            if choice != "file":
                return
        extensions = " ".join(f"*{suffix}" for suffix in IMAGE_EXTENSIONS)
        file_name = prompts.choose_open_file(self.window, t('set_mod_image'), t('images_value0', value0=f'{extensions}'))
        if file_name:
            self.apply(PreviewSource(Path(file_name)), names)

    def apply(self, source: PreviewSource, names: list[str] | None = None, confirmed: bool = False) -> None:
        submitted = False
        try:
            if self.window.busy:
                return
            names = list(names if names is not None else self.window._selected_mod_names())
            image = read_preview_image(source.path)
            if image.isNull():
                prompts.show_error(self.window, t('text_1e63fa10de76'), t('this_image_could_not_be_read_choose_another_image'))
                return
            if not names:
                name = self.window._choose_mod_for_image()
                if not name:
                    return
                names = [name]
            if len(names) > 1 and not confirmed:
                if prompts.choose_preview_image(self.window, source.path, len(names)) != "apply":
                    return
            cfg = dict(self.window.cfg)

            def worker():
                try:
                    with tempfile.TemporaryDirectory(prefix="mods-preview-") as staging:
                        path = Path(staging) / "preview.png"
                        if not image.save(str(path), "PNG"):
                            raise OSError(t('cannot_prepare_the_preview_image'))
                        return import_mod_images(cfg, names, path)
                finally:
                    source.close()

            def done(result):
                applied, errors = result
                for name in applied:
                    self.window._invalidate_mod_image(name)
                self.window.refresh_mods(names)
                self.window._set_status(t('preview_images_updated_value0_failed_value1', value0=f'{len(applied)}', value1=f'{len(errors)}'))
                if errors:
                    prompts.show_warning(self.window, t('text_1e63fa10de76'), "\n".join(errors))

            self.window._run_action(t('setting_preview_images'), worker, done)
            submitted = True
        finally:
            if not submitted:
                source.close()
