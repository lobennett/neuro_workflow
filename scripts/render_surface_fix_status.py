"""Render the SURFACE-FIX-STATUS.md table comparing pre- vs post-fix hole counts."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


def render_status(pre_tsv: Path, post_tsv: Path, threshold: int) -> str:
    pre = pd.read_csv(pre_tsv, sep='\t')
    post = pd.read_csv(post_tsv, sep='\t')

    rows = []
    for _, p in pre.iterrows():
        q = post.loc[post['subject'] == p['subject']]
        if len(q) == 0:
            continue
        q = q.iloc[0]
        decision = 'KEEP' if q['fs_holes_mean'] <= threshold else 'EXCLUDE'
        rows.append({
            'subject': p['subject'],
            'pre': f"{p['fs_holes_mean']:.0f}",
            'post': f"{q['fs_holes_mean']:.0f}",
            'decision': decision,
        })

    lines = [
        '# Surface fix status',
        '',
        f'Threshold: mean post-fix Euler holes ≤ {threshold} → KEEP',
        '',
        '| Subject | Pre mean holes | Post mean holes | Decision |',
        '|---|---|---|---|',
    ]
    for r in rows:
        lines.append(f'| {r["subject"]} | {r["pre"]} | {r["post"]} | {r["decision"]} |')
    return '\n'.join(lines) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pre-cohort-tsv', type=Path, required=True)
    parser.add_argument('--post-cohort-tsv', type=Path, required=True)
    parser.add_argument('--threshold', type=int, default=100)
    parser.add_argument('--output-md', type=Path, default=None)
    args = parser.parse_args()

    md = render_status(args.pre_cohort_tsv, args.post_cohort_tsv, args.threshold)
    if args.output_md:
        args.output_md.write_text(md)
        print(f'Wrote {args.output_md}')
    else:
        print(md)
    return 0


if __name__ == '__main__':
    sys.exit(main())
