#!/bin/bash
#SBATCH -J happy_{dataset_name}
#SBATCH --time={time}
#SBATCH -n 1
#SBATCH --array=1-{n_scans}
#SBATCH --cpus-per-task={nthreads}
#SBATCH --mem-per-cpu={mem_per_cpu_gb}G
#SBATCH -p {partition}
#SBATCH -o {log_dir}/%x-%A-%a.out
#SBATCH -e {log_dir}/%x-%A-%a.err
{mail_line}

set -euo pipefail

LIST_FILE="{scan_list_file}"
LINE="$(sed -n "${{SLURM_ARRAY_TASK_ID}}p" "$LIST_FILE")"

if [ -z "$LINE" ]; then
    echo "ERROR: No data at line ${{SLURM_ARRAY_TASK_ID}} in ${{LIST_FILE}}" >&2
    exit 1
fi

read -r BOLD_FILE BOLD_JSON PHYS_TSV PHYS_JSON OUT_FILE <<< "$LINE"
OUT_PREFIX="${{OUT_FILE%.nii.gz}}"

# Skip if output exists
if compgen -G "${{OUT_PREFIX}}_"* > /dev/null 2>&1; then
    echo "SKIPPED: Output already exists for ${{BOLD_FILE}}"
    exit 0
fi

mkdir -p "$(dirname "$OUT_PREFIX")"

CONTAINER="{image_path}"

singularity exec "$CONTAINER" happy \
    --cardiacfile "${{PHYS_TSV}}:cardiac" \
    --temporalregression \
    {happy_args} \
    "$BOLD_FILE" \
    "$BOLD_JSON" \
    "$OUT_PREFIX"

exitcode=$?
echo "Task ${{SLURM_ARRAY_TASK_ID}} finished with exit code $exitcode"
exit $exitcode
