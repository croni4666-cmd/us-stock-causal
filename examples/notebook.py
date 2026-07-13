"""
examples/notebook.py - Jupyter Lab 启动器 (Phase 4 P4-2)

用法:
  python examples/notebook.py             # 默认端口 8888
  python examples/notebook.py --port 8889 # 自定义端口
  python examples/notebook.py --no-browser  # 不开浏览器 (headless / SSH)

依赖: jupyterlab, nbformat, ipykernel
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Launch Jupyter Lab for us-stock-causal self-analysis"
    )
    parser.add_argument("--port", type=int, default=8888, help="Jupyter port (default 8888)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser")
    parser.add_argument(
        "--ip", default="127.0.0.1",
        help="Bind IP (default 127.0.0.1, change to 0.0.0.0 for LAN access)"
    )
    args = parser.parse_args()

    print("=" * 72)
    print(f"us-stock-causal v0.5.0 - Jupyter Lab launcher (Phase 4 P4-2)")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Notebook dir:  {PROJECT_ROOT / 'notebooks'}")
    print(f"Cache dir:     {PROJECT_ROOT / 'data' / 'raw'}")
    print(f"Output dir:    {PROJECT_ROOT / 'output'}")
    print("=" * 72)
    print()
    print("Sample notebooks (auto-loaded if in notebooks/):")
    nb_dir = PROJECT_ROOT / "notebooks"
    if nb_dir.exists():
        for p in sorted(nb_dir.glob("*.ipynb")):
            print(f"  📓 {p.name}")
    else:
        print("  (no notebooks/ dir yet)")
    print()
    print(f"Starting Jupyter Lab on http://{args.ip}:{args.port}")
    print("Press Ctrl+C to stop.")
    print("=" * 72)

    cmd = [
        sys.executable, "-m", "jupyter", "lab",
        "--port", str(args.port),
        "--ip", args.ip,
        "--notebook-dir", str(PROJECT_ROOT),
    ]
    if args.no_browser:
        cmd.append("--no-browser")
    else:
        cmd.append("--browser=default")

    try:
        return subprocess.call(cmd, cwd=PROJECT_ROOT)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
