#!/bin/bash
#SBATCH --job-name=lev1_outliers
#SBATCH --partition=russpold
#SBATCH --time=01:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=2
#SBATCH --output=logs/lev1_outliers-%j.out
#SBATCH --error=logs/lev1_outliers-%j.err

set -euo pipefail
cd /home/users/logben/neuro_workflow
mkdir -p logs

module load uv
uv run python scripts/lev1_outliers.py "$@"
