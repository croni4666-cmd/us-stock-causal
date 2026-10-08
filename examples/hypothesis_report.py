"""Offline registered observable checks; no web lookup or implicit fact generation."""
import argparse
import json
from pathlib import Path
import sys

import pandas as pd
from src.hypothesis_review import evaluate_registry, render_hypothesis_report


def main(argv=None):
    parser=argparse.ArgumentParser(description='Low-trust DAG and falsifiable observable hypothesis review')
    parser.add_argument('--registry',type=Path,required=True)
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('output/hypothesis_report.md'))
    parser.add_argument('--json-output',type=Path)
    args=parser.parse_args(argv)
    try:
        registry=json.loads(args.registry.read_text(encoding='utf-8-sig'))
        result=evaluate_registry(registry,pd.read_parquet(args.data))
        # Refuse unserializable/nonfinite results before writing a partial success.
        encoded=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(render_hypothesis_report(result),encoding='utf-8')
        if args.json_output:
            args.json_output.parent.mkdir(parents=True,exist_ok=True)
            args.json_output.write_text(encoded,encoding='utf-8')
        print(f'Observable hypothesis report saved to {args.output}')
        return 0
    except (ValueError,TypeError,OSError) as exc:
        print(f'Hypothesis report failed: {exc}',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
