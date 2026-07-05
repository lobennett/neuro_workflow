# Contributing to neuro-workflow

## Branch naming

Prefix every branch with its type, then a short slug:

```
fix/<slug>
feat/<slug>
refactor/<slug>
docs/<slug>
chore/<slug>
test/<slug>
```

Example: `fix/lev1-vif-threshold`, `chore/ci-and-standards`.

## PR titles

Titles follow a Conventional-Commits-style prefix in caps, matching the branch type:

```
FIX: ...
FEAT: ...
REFACTOR: ...
DOCS: ...
CHORE: ...
TEST: ...
```

Keep the summary short (under ~70 chars); put detail in the PR description.

## Commit trailer

Commits authored with Claude Code assistance carry a `Co-Authored-By:` trailer,
matching the existing project convention:

```bash
git add <files>
git commit -m "feat|fix|refactor: <description>

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

Use whichever assistant/model actually did the work in the trailer. Human-only
commits omit the trailer.

## Dev setup

```bash
module load uv/0.9.5
uv sync --all-extras
uv run pre-commit install
```

`uv sync --all-extras` pulls in the `lev1`, `qa`, `bidsify`, `events`, and
`datalad` optional dependency groups plus the `dev` dependency group
(pytest, ruff, pre-commit).

## Tests

Core suite (what CI runs):

```bash
uv run pytest tests/ --ignore=tests/analysis
```

`tests/analysis/` requires heavy neuroimaging dependencies (nibabel, nilearn,
statsmodels) and/or real HPC-scale data and is **excluded from CI**. Run it
locally/on-cluster when touching `lev1`/`lev2`/`mshbm` analysis code:

```bash
uv run pytest tests/analysis -v
```

## Lint

```bash
uv run ruff check .
uv run ruff format --check .
```

`uv run pre-commit run --all-files` runs the same ruff checks plus codespell
and whitespace/EOF/YAML hygiene hooks (see `.pre-commit-config.yaml`).

## Sherlock note

**Never run the pytest suite (or any nontrivial Python) on the login node.**
Use an interactive shell or a job:

```bash
sh_dev                                   # quick interactive shell
srun --pty --time=00:30:00 --mem=8G bash # or salloc for something longer
```

or submit via `sbatch` for anything long-running or resource-heavy.

## Public API note

`neuro_workflow.core.slurm` and `neuro_workflow.pipelines.base` are imported
by the separate `network_analysis` repository. Don't change their public
interfaces (function/class signatures, module-level names) without
coordinating — a breaking change here breaks that downstream repo silently
until someone runs it.
