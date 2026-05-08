#!/bin/bash
#SBATCH -J lev2_{dataset_name}
#SBATCH --array=1-{n_contrasts}
#SBATCH --cpus-per-task={nthreads}
#SBATCH --mem={mem_gb}G
#SBATCH --time={time}
#SBATCH -p {partition}
#SBATCH -o {log_dir}/%x-%A-%a.out
#SBATCH -e {log_dir}/%x-%A-%a.err
{mail_line}

CONTRAST="$(sed -n "${{SLURM_ARRAY_TASK_ID}}p" "{contrast_list_file}")"

module load biology fsl
module load uv

uv --directory "{neuro_workflow_dir}" run python -m neuro_workflow.analysis.lev2.run \
    --contrast "$CONTRAST" \
    --level1-dirs {lev1_dirs} \
    --output-dir "{results_dir}" \
    --mask-threshold {mask_threshold} \
    --num-permutations {num_permutations}
