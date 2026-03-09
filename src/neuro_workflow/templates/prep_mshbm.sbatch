#!/bin/bash
#SBATCH -J prep_mshbm_{dataset_name}
#SBATCH --array=1-{n_subjects}
#SBATCH --cpus-per-task={nthreads}
#SBATCH --mem={mem_gb}G
#SBATCH --time={time}
#SBATCH -p {partition}
#SBATCH -o {log_dir}/%x-%A-%a.out
#SBATCH -e {log_dir}/%x-%A-%a.err
{mail_line}

SUBJ_ID="$(sed -n "${{SLURM_ARRAY_TASK_ID}}p" "{subject_list_file}")"

module load biology freesurfer/8.1.0
module load biology ants/2.4.0
module load uv

uv --directory "{neuro_workflow_dir}" run network-prep-mshbm \
    --subj-id "$SUBJ_ID" \
    --glm-dir "{glm_dir}" \
    --fmriprep-dir "{fmriprep_dir}" \
    --output-dir "{output_dir}" \
    --residuals-space {residuals_space} {extra_flags}
