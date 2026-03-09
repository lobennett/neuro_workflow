#!/bin/bash
#SBATCH --job-name=mshbm_{dataset_name}
#SBATCH --cpus-per-task={nthreads}
#SBATCH --mem={mem_gb}G
#SBATCH --time={time}
#SBATCH -p {partition}
#SBATCH -o {output_dir}/logs/%x-%j.out
#SBATCH -e {output_dir}/logs/%x-%j.err
{mail_line}

module load matlab

bash "{mshbm_dir}/MSHBM/run_MSHBM.sh" "{sub_list_file}" "{output_dir}" "{mshbm_dir}"
