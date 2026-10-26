#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import sys

if __name__ == "__main__":
    try:
        if len(sys.argv) > 1:
            from mod_manager.cli import run_cli

            raise SystemExit(run_cli(sys.argv[1:]))
        else:
            from mod_manager.menus import main_menu

            raise SystemExit(main_menu())
    except KeyboardInterrupt:
        print("\nExit…")
        raise SystemExit(130)
