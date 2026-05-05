#!/bin/bash
#SBATCH -J fmriprep_{dataset_name}
#SBATCH --time={time}
#SBATCH -n 1
#SBATCH --array=1-{n_subjects}%{array_throttle}
#SBATCH --cpus-per-task={nthreads}
#SBATCH --mem-per-cpu={mem_per_cpu_gb}G
#SBATCH -p {partition}
#SBATCH -o {log_dir}/%x-%A-%a.out
#SBATCH -e {log_dir}/%x-%A-%a.err
{mail_line}

subject=$(sed "${{SLURM_ARRAY_TASK_ID}}q;d" {subjects_file} | tr -d '\r')

FMRIPREP_IMG="{image_path}"

mkdir -p "{work_dir}"

apptainer run --cleanenv \
  --env TEMPLATEFLOW_HOME=/templateflow \
  -B {bids_dir}:/data \
  -B {templateflow_dir}:/templateflow \
  -B {work_dir}:/work \
{config_bind_line}{output_bind_line}  "$FMRIPREP_IMG" \
  /data {output_container}/fmriprep_{fmriprep_version} participant \
  --participant-label "$subject" \
  -w /work \
  --nthreads {nthreads} \
  --mem_mb {mem_mb} \
  --output-spaces {output_spaces} \
  --fs-license-file {fs_license_container} \
  {bids_filter_arg} \
  {fmriprep_args} \
  --verbose

exitcode=$?

# Workaround for fmriprep#3634 (fix in PR #3636, not yet in any LTS release):
# fmriprep 25.2.4 (verified at the success-message string "fMRIPrep finished
# successfully") occasionally exits with code 1 after a successful workflow due
# to a typo bug in the post-workflow report generator. If the workflow log
# contains the success message, treat exit-1 as success. When upgrading
# fmriprep, verify this string is still produced or remove this block.
#
# Lustre flush note: the .out file lives on /scratch (Lustre). Brief sync+sleep
# ensures the trailing lines from apptainer's stdio buffer are visible to grep.
log_file="{log_dir}/fmriprep_{dataset_name}-${{SLURM_ARRAY_JOB_ID}}-${{SLURM_ARRAY_TASK_ID}}.out"
sync
sleep 2
if [ "$exitcode" -eq 1 ] && [ -f "$log_file" ] && grep -q "fMRIPrep finished successfully" "$log_file"; then
  echo "Detected fmriprep#3634 benign exit-1 (workflow finished successfully); treating as exit 0."
  exitcode=0
fi

# Cleanup per-subject work dir on confirmed success only. On real failures the
# work dir is preserved so the next sbatch resubmit can resume from cached nodes.
if [ "$exitcode" -eq 0 ]; then
  subject_work="{work_dir}/sub-${{subject}}"
  if [ -d "$subject_work" ]; then
    if rm -rf "$subject_work"; then
      echo "Cleaned up work dir on success: $subject_work"
    else
      echo "WARNING: cleanup failed for $subject_work (scratch may be full)"
    fi
  fi
fi

echo "Task ${{SLURM_ARRAY_TASK_ID}} ($subject) finished with exit code $exitcode"
exit $exitcode
