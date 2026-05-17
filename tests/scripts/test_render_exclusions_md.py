"""Tests for scripts/render_exclusions_md.py."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parents[2] / 'scripts' / 'render_exclusions_md.py'
    spec = importlib.util.spec_from_file_location('render_excl', script_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules['render_excl'] = mod
    spec.loader.exec_module(mod)
    return mod


def _sample_compiled():
    return {
        'entries': [
            {'subject': 'sub-s03', 'session': '-', 'task': '-', 'run': '-',
             'source': 'qa_decisions', 'reason': 'surface_quality: 324 holes'},
            {'subject': 'sub-s10', 'session': '04', 'task': 'cuedTS', 'run': '1',
             'source': 'motion', 'reason': 'mean FD > 0.5'},
            {'subject': 'sub-s10', 'session': '07', 'task': 'rest', 'run': '1',
             'source': 'behavioral', 'reason': 'omission > 25%'},
        ],
    }


def test_render_md_groups_by_source(tmp_path):
    mod = _load_module()
    p = tmp_path / 'compiled.json'
    p.write_text(json.dumps(_sample_compiled()))

    md = mod.render_md({'discovery': p})
    assert '## discovery' in md
    assert '### Source: qa_decisions' in md
    assert '### Source: motion' in md
    assert '### Source: behavioral' in md
    assert 'sub-s03' in md
    assert 'mean FD > 0.5' in md


def test_render_md_handles_multiple_cohorts(tmp_path):
    mod = _load_module()
    p_disc = tmp_path / 'disc.json'
    p_disc.write_text(json.dumps(_sample_compiled()))
    p_val = tmp_path / 'val.json'
    p_val.write_text(json.dumps({'entries': []}))

    md = mod.render_md({'discovery': p_disc, 'validation': p_val})
    assert '## discovery' in md
    assert '## validation' in md
    assert '(no exclusions)' in md
