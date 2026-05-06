#!/bin/bash
#SBATCH --job-name=qa_report
#SBATCH --partition=russpold
#SBATCH --time=12:00:00
#SBATCH --mem=128G
#SBATCH --cpus-per-task=6
#SBATCH --output=logs/qa_report-%j.out
#SBATCH --error=logs/qa_report-%j.err

# Generate QA HTML cohort dashboard with reliability movies.
# brm needs ffmpeg + cairo libs and enough RAM to load 1mm BOLDs.
# Args after the script path are passed through to scripts/qa_report.py.
set -euo pipefail

cd /home/users/logben/neuro_workflow
mkdir -p logs

module load uv ffmpeg/7.1 cairo
export LD_LIBRARY_PATH="/share/software/user/open/cairo/1.14.10/lib:${LD_LIBRARY_PATH:-}"
# brm CLI is installed via `uv tool install` and lives in ~/.local/bin
export PATH="${HOME}/.local/bin:${PATH}"

uv run python scripts/qa_report.py "$@"
