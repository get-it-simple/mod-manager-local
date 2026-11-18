from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

from PySide6 import QtCore, QtTest

from mod_manager.i18n import t
from mod_manager.models import OperationItem, OperationResult
from mod_manager.storage_policy import profile_config
from mod_manager.ui.task_runner import TaskRunner
from mod_manager.ui.widgets.sidebar_labels import SidebarLabels
from tests.gui_background import DeferredRunner
from tests.qt_support import qt_app
from tests.window_fixture import WindowTestCase, mod_item


class OperationQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def setUp(self):
        self.runner = TaskRunner()
        self.deferred = DeferredRunner()
        self.runner.background = self.deferred.background
        self.addCleanup(self.runner.shutdown)

    def test_fifo_pins_context_and_finishes_callback_before_next_work(self):
        events = []
        cfg = {"active_game_profile_id": "synthetic-first"}
        self.runner.run("first", lambda: events.append(("work", profile_config()["active_game_profile_id"])),
                        lambda _value: events.append(("done", "first")), config=cfg, mod_names=("one.pak",), blocking=False)
        cfg["active_game_profile_id"] = "synthetic-second"
        self.runner.run("second", lambda: events.append(("work", profile_config()["active_game_profile_id"])),
                        lambda _value: events.append(("done", "second")), config=cfg, mod_names=("two.pak",), blocking=False)
        self.assertFalse(self.runner.busy)
        self.assertEqual(self.runner.pending_mods, {"one.pak", "two.pak"})
        self.assertEqual(len(self.deferred.jobs), 1)
        self.deferred.complete()
        self.assertEqual(events, [("work", "synthetic-first"), ("done", "first")])
        self.assertEqual(self.runner.pending_mods, {"two.pak"})
        self.deferred.complete()
        self.assertEqual(events[-2:], [("work", "synthetic-second"), ("done", "second")])
        self.assertFalse(self.runner.commands)

    def test_failure_and_declined_preflight_release_targets_and_continue(self):
        events, errors = [], []
        self.runner.failed.connect(errors.append)
        self.runner.run("failed", lambda: (_ for _ in ()).throw(OSError("synthetic failure")), blocking=False,
                        mod_names=("one.pak",))
        self.runner.run("declined", lambda: events.append("incorrect"), prepare=lambda: False, blocking=False)
        self.runner.run("last", lambda: events.append("last"), blocking=False)
        self.deferred.complete()
        self.assertEqual(errors, ["synthetic failure"])
        self.assertEqual(len(self.deferred.jobs), 1)
        self.assertEqual(self.runner.pending_mods, set())
        self.deferred.complete()
        self.assertEqual(events, ["last"])

    def test_confirmations_finish_before_later_commands_dispatch(self):
        events = []
        self.runner.run("first", lambda: events.append("first"), blocking=False)
        self.runner.run("confirmed", lambda: events.append("confirmed"),
                        prepare=lambda: events.append("confirmation") or True, blocking=False)
        self.runner.run("third", lambda: events.append("third"), blocking=False)
        self.assertEqual(events, [])
        self.deferred.complete()
        self.assertEqual(events, ["first", "confirmation"])
        self.deferred.complete()
        self.deferred.complete()
        self.assertEqual(events, ["first", "confirmation", "confirmed", "third"])

    def test_nested_window_fixture_patches_restore_the_original_functions(self):
        from mod_manager import storage
        from mod_manager.ui import app

        originals = app.mods_view, storage.save_config
        case = WindowTestCase()
        case.qt_app = self.app
        case.setUp()
        inner = patch("mod_manager.ui.app.mods_view", wraps=app.mods_view)
        inner.start()
        try:
            case.tearDown()
        finally:
            inner.stop()
            case.doCleanups()
        self.assertIs(app.mods_view, originals[0])
        self.assertIs(storage.save_config, originals[1])


class QueueGuiTests(WindowTestCase):
    def setUp(self):
        super().setUp()
        self.deferred = DeferredRunner()
        self.window.runner.background = self.deferred.background

    def finish_commands(self):
        while self.deferred.jobs:
            self.deferred.complete()

    def test_other_mod_can_be_queued_and_duplicate_target_is_blocked(self):
        self.select_mod_rows(1)
        result = OperationResult((OperationItem("ui.pak", "installed", True, "OK"),))
        with patch("mod_manager.ui.app.change_mods", return_value=result) as change:
            self.window._install_selected_mods()
            self.assertEqual(self.window.runner.pending_mods, {"ui.pak"})
            self.assertFalse(self.window.mods_actions.button("install_selected").isEnabled())
            self.select_mod_rows(0)
            self.assertTrue(self.window.mods_actions.button("uninstall_selected").isEnabled())
            self.assertTrue(self.window.workspace.navigation["presets"].isEnabled())
            self.window._uninstall_selected_mods()
            self.window._uninstall_selected_mods()
            self.assertEqual(len(self.window.runner.commands), 2)
            self.finish_commands()
            self.assertEqual(change.call_count, 2)
        self.assertFalse(self.window.runner.pending_mods)

    def test_large_unicode_page_counts_exclude_reserved_mods_and_recover_after_completion(self):
        self.mods[:] = [mod_item(f"中文😀-{index}.pak", installed=index % 2 == 0) for index in range(1000)]
        self.window.refresh_mods()
        self.finish_commands()
        reserved = tuple(mod.name for index, mod in enumerate(self.mods) if index % 4 in (0, 1))
        self.window.runner.run("Synthetic large operation", lambda: None, config=self.window.cfg,
                               mod_names=reserved, blocking=False)
        for key in ("install_page", "uninstall_page"):
            self.assertEqual(self.window.mods_actions.button(key).text(), t(key, count=250))
            self.assertTrue(self.window.mods_actions.button(key).isEnabled())
        self.finish_commands()
        for key in ("install_page", "uninstall_page"):
            self.assertEqual(self.window.mods_actions.button(key).text(), t(key, count=500))
            self.assertTrue(self.window.mods_actions.button(key).isEnabled())

    def test_page_targets_remain_fixed_when_filters_change_while_queued(self):
        self.window._run_action("earlier operation", lambda: None)
        with patch("mod_manager.ui.app.change_mods_page", return_value=(1, OperationResult())) as change:
            self.window._install_page()
            self.window.filters.add("search", "different")
            self.finish_commands()
        targets = change.call_args.kwargs["targets"]
        self.assertEqual([mod.name for mod in targets], ["ui.pak"])
        self.assertEqual(change.call_args.args[3], ())

    def test_close_waits_for_queue_and_can_be_cancelled(self):
        self.window._run_action("pending", lambda: None, mod_names=("ui.pak",))
        event = QtCore.QEvent(QtCore.QEvent.Close)
        self.window.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertTrue(self.window._closing_after_queue)
        self.assertFalse(self.window.runner._closed)
        self.window._cancel_queued_close()
        self.assertFalse(self.window._closing_after_queue)
        self.finish_commands()
        self.assertFalse(self.window.runner._closed)

    def test_profile_switch_waits_behind_existing_mutation(self):
        from mod_manager.storage import create_game_profile

        second = create_game_profile("Synthetic second", {"mods_source_dir": "other-source", "game_mods_dir": "other-game"},
                                     self.window.cfg)
        first = self.window.cfg["game_profiles"][0]["id"]
        self.window.cfg["active_game_profile_id"] = first
        self.window._run_action("pending", lambda: None)
        with patch("mod_manager.ui.controllers.games_controller.save_config"):
            self.window._select_game_profile(second["id"])
            self.assertEqual(self.window.cfg["active_game_profile_id"], first)
            self.assertTrue(self.window.runner.barrier_pending)
            self.assertFalse(self.window.mods_actions.button("install_page").isEnabled())
            self.finish_commands()
        self.assertEqual(self.window.cfg["active_game_profile_id"], second["id"])

    def test_selecting_another_mod_during_work_keeps_new_selection(self):
        self.select_mod_rows(1)
        self.window._run_action("pending", lambda: None, mod_names=("ui.pak",))
        self.select_mod_rows(0)
        self.finish_commands()
        self.assertEqual(self.window._selected_mod_names(), ["combat.pak"])

    def test_later_view_choice_survives_an_earlier_settings_save(self):
        self.window.settings.save()
        self.window._set_view_mode("tiles")
        self.finish_commands()
        self.assertEqual(self.window.cfg["mod_view_mode"], "tiles")
        self.assertTrue(self.window._is_tile_view())


class SidebarLabelActionTests(WindowTestCase):
    def test_plain_activation_replaces_filters_and_shift_toggles_only_label(self):
        window = self.window
        window.filters.add("label", "previous")
        window.filters.add("search", "text")
        window.filters.mode = "favorite"
        window._sidebar_label_requested("combat")
        self.assertEqual(window.filters.labels, ("combat",))
        self.assertEqual(window.filters.queries, ())
        self.assertEqual(window.filters.mode, "all")
        window.filters.add("search", "combat")
        window.filters.mode = "installed"
        window._sidebar_label_requested("combat", True)
        self.assertEqual(window.filters.labels, ())
        self.assertEqual(window.filters.queries, ("combat",))
        self.assertEqual(window.filters.mode, "installed")

    def test_hover_plus_and_shift_keyboard_emit_only_additive_action(self):
        view = SidebarLabels()
        self.addCleanup(view.deleteLater)
        view.update_labels([("Synthetic label", "manual", 1, False)], self.window.theme.system_accent)
        view.resize(240, 120)
        view.show()
        self.qt_app.processEvents()
        index = view.model().index(0, 0)
        view.setCurrentIndex(index)
        plain = QtTest.QSignalSpy(view.labelRequested)
        additive = QtTest.QSignalSpy(view.labelToggleRequested)
        size = view.sizeHint()
        for compact in (False, True):
            view.set_compact(compact)
            point = view.delegate.add_rect(view.visualRect(index)).center()
            QtTest.QTest.mouseMove(view.viewport(), point)
            QtTest.QTest.mouseClick(view.viewport(), QtCore.Qt.LeftButton, pos=point)
            self.assertEqual(plain.count(), int(compact))
            if compact:
                self.assertFalse(view.add_button.isVisible())
        self.assertEqual(additive.count(), 1)
        QtTest.QTest.keyClick(view, QtCore.Qt.Key_Return, QtCore.Qt.ShiftModifier)
        self.assertEqual(additive.count(), 2)
        self.assertEqual(view.sizeHint(), size)
