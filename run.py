#!/usr/bin/env python3
"""Launch Easy Clipboard Manager from a source checkout.

Usage:  python run.py [--background] [--verbose]
"""

from __future__ import annotations

import sys

from easy_clipboard.app import run

if __name__ == "__main__":
    sys.exit(run())
