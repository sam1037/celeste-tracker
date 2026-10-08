#!/usr/bin/env python3
"""Entry point for the desktop app (`uv run --extra desktop celeste_desktop.py`) and the PyInstaller build."""
from celeste_tracker.desktop import main

if __name__ == "__main__":
    main()
