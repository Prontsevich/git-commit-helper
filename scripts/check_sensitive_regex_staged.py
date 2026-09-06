#!/usr/bin/env python3
"""Compatibility alias: the scanner now lives in check_secrets.py."""

from __future__ import annotations

import os
import runpy
import sys

TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "check_secrets.py")

if __name__ == "__main__":
    sys.argv[0] = TARGET
    runpy.run_path(TARGET, run_name="__main__")
