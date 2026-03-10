#!/bin/bash
#SBATCH -J lev1_{dataset_name}
#SBATCH --array=1-{n_jobs}
#SBATCH --cpus-per-task={nthreads}
#SBATCH --mem={mem_gb}G
#SBATCH --time={time}
#SBATCH -p {partition}
#SBATCH -o {log_dir}/%x-%A-%a.out
#SBATCH -e {log_dir}/%x-%A-%a.err
{mail_line}

LINE="$(sed -n "${{SLURM_ARRAY_TASK_ID}}p" "{job_list_file}")"
read -r SUBJ_ID TASK_NAME <<< "$LINE"

module load uv

uv --directory "{neuro_workflow_dir}" run python -m neuro_workflow.analysis.lev1.run \
    --subj-id "$SUBJ_ID" \
    --task-name "$TASK_NAME" \
    --bids-dir "{bids_dir}" \
    --fmriprep-dir "{fmriprep_dir}" \
    --results-dir "{results_dir}" \
    --exclusions-file "{exclusions_file}" \
    --space {space} \
    --within-subject-threshold {threshold} {extra_flags}
