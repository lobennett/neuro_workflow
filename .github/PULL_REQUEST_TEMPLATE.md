## Summary

<!-- what & why -->

## Type
- [ ] FIX  - [ ] FEAT  - [ ] REFACTOR  - [ ] DOCS  - [ ] CHORE  - [ ] TEST

## Checklist
- [ ] Branch named `<type>/<slug>`; PR title `TYPE: ...`
- [ ] `uv run ruff check . && uv run ruff format --check .` clean
- [ ] Core suite green (`uv run pytest tests/ --ignore=tests/analysis`) or CI green
- [ ] Docs updated if behavior/commands changed
- [ ] No change to public API (`core.slurm`, `pipelines.base`) without noting downstream `network_analysis`
