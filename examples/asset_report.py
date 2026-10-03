"""Explicit issuer sync or offline asset report: python -m examples.asset_report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from src.asset_models import ASSET_KINDS
from src.asset_report import build_asset_report, render_asset_report
from src.asset_sources import SOURCE_SPECS, capture_source


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Official asset inputs and asset-specific reports")
    commands = parser.add_subparsers(dest="command", required=True)
    sync = commands.add_parser("sync", help="Download official sources explicitly")
    sync.add_argument("--symbols", nargs="+", choices=SOURCE_SPECS, default=list(SOURCE_SPECS))
    sync.add_argument("--source-root", type=Path, default=Path("data/asset_sources"))
    report = commands.add_parser("report", help="Use local data only; never fetch")
    report.add_argument("--symbols", nargs="+", choices=ASSET_KINDS, default=["GLD", "GC=F", "IEF", "TLT", "QQQ", "^NDX", "^IXIC"])
    report.add_argument("--source-root", type=Path, default=Path("data/asset_sources"))
    report.add_argument("--market-root", type=Path, default=Path("data/raw"))
    report.add_argument("--start", required=True)
    report.add_argument("--end", required=True)
    report.add_argument("--mode", choices=("point_in_time", "retrospective"), default="point_in_time")
    report.add_argument("--output", type=Path, default=Path("output/asset_report.md"))
    report.add_argument("--json-output", type=Path)
    report.add_argument("--market-file", action="append", default=[], metavar="SYMBOL=PATH",
                        help="Explicit cache selection when a symbol exists in multiple layers; repeatable")
    args = parser.parse_args(argv)
    if args.command == "sync":
        failures = 0
        for symbol in args.symbols:
            try:
                path = capture_source(symbol, args.source_root)
                print(f"{symbol}: saved official evidence to {path}")
            except Exception as exc:
                failures += 1
                print(f"{symbol}: failed: {exc}", file=sys.stderr)
        return 1 if failures else 0
    try:
        market_files = {}
        for entry in args.market_file:
            # Futures symbols contain '='; the separator is the last '=' before
            # a path. Ordinary paths may contain '=', so prefer the known symbol.
            symbol = next((s for s in ASSET_KINDS if entry.startswith(s + '=')), None)
            if symbol is None:
                symbol, separator, path = entry.partition('=')
                if not separator or not path:
                    raise ValueError("market-file must be SYMBOL=PATH")
            else:
                path = entry[len(symbol) + 1:]
            if symbol in market_files or not path:
                raise ValueError("duplicate symbol or empty market-file path")
            market_files[symbol] = Path(path)
        result = build_asset_report(args.symbols, args.start, args.end, args.market_root, args.source_root,
                                    mode=args.mode, market_files=market_files)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render_asset_report(result), encoding="utf-8")
        if args.json_output:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        print(f"Report saved to {args.output}")
        # Incomplete financial inputs are documented in a valid partial report;
        # invalid arguments or failure to write a report are command failures.
        return 0
    except (ValueError, OSError) as exc:
        print(f"Report failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    raise SystemExit(main())
