#!/bin/bash
#SBATCH -J freesurfer_{dataset_name}
#SBATCH --time={time}
#SBATCH -n 1
#SBATCH --array=1-{n_subjects}
#SBATCH --cpus-per-task={nthreads}
#SBATCH --mem-per-cpu={mem_per_cpu_gb}G
#SBATCH -p {partition}
#SBATCH -o {log_dir}/%x-%A-%a.out
#SBATCH -e {log_dir}/%x-%A-%a.err
{mail_line}

SINGULARITY_IMG="{image_path}"
export FS_LICENSE="{fs_license}"

# Read subject info from CSV: subject_id,ses_t1,run_t1,ses_t2,run_t2
line=$(sed -n "${{SLURM_ARRAY_TASK_ID}}p" {fs_subjects_file})
IFS=',' read -r subject_id ses_t1 run_t1 ses_t2 run_t2 <<< "$line"
subject="sub-${{subject_id}}"

t1w_path="{bids_dir}/${{subject}}/${{ses_t1}}/anat/${{subject}}_${{ses_t1}}_run-${{run_t1}}_T1w.nii.gz"

DERIVS_DIR="{bids_dir}/derivatives/freesurfer_{freesurfer_version}"
mkdir -p "$DERIVS_DIR"

if [ -n "$ses_t2" ]; then
    t2w_path="{bids_dir}/${{subject}}/${{ses_t2}}/anat/${{subject}}_${{ses_t2}}_run-${{run_t2}}_T2w.nii.gz"
    singularity exec --bind {bids_dir}:{bids_dir},${{FS_LICENSE}}:${{FS_LICENSE}} \
        "$SINGULARITY_IMG" recon-all \
        -i "$t1w_path" \
        -T2 "$t2w_path" \
        -s "$subject" \
        -sd "$DERIVS_DIR" \
        -all
else
    singularity exec --bind {bids_dir}:{bids_dir},${{FS_LICENSE}}:${{FS_LICENSE}} \
        "$SINGULARITY_IMG" recon-all \
        -i "$t1w_path" \
        -s "$subject" \
        -sd "$DERIVS_DIR" \
        -all
fi

exitcode=$?
echo "Task ${{SLURM_ARRAY_TASK_ID}} ($subject) finished with exit code $exitcode"
exit $exitcode
