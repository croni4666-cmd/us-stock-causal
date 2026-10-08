#!/usr/bin/env python3
"""Offline exploratory NVDA model scenarios, using the maintained OLS example.

The former handwritten DAG, automatic downloads and catalyst attribution are
retired because their causal identification and evidence were not established.
Use --cache-root with explicit cached log returns and --date with an exact day.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from examples import nvda_cf_lite


def main(argv=None):
    return nvda_cf_lite.main(argv)


if __name__ == '__main__':
    sys.exit(main())
