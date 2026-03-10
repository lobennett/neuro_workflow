#!/bin/bash
#SBATCH -J bidsify_{sample}
#SBATCH --time={time}
#SBATCH -n 1
#SBATCH --cpus-per-task={cpus}
#SBATCH --mem={mem_gb}G
#SBATCH -p {partition}
#SBATCH -o {log_dir}/%x-%j.out
#SBATCH -e {log_dir}/%x-%j.err
{mail_line}

set -euo pipefail

mkdir -p "{log_dir}"

CONTAINER="{container}"

apptainer run "$CONTAINER" bidsify {sample} \
    --output-dir {output_dir} \
    {extra_args}

exitcode=$?
echo "Bidsify finished with exit code $exitcode"
exit $exitcode
