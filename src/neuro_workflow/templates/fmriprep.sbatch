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

subject=$(sed "${{SLURM_ARRAY_TASK_ID}}q;d" {subjects_file})

FMRIPREP_IMG="{image_path}"

mkdir -p "{work_dir}"

apptainer run --cleanenv \
  --env TEMPLATEFLOW_HOME=/templateflow \
  -B {bids_dir}:/data \
  -B {templateflow_dir}:/templateflow \
  -B {work_dir}:/work \
  {config_bind_line} \
  "$FMRIPREP_IMG" \
  /data /data/derivatives/fmriprep_{fmriprep_version} participant \
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
echo "Task ${{SLURM_ARRAY_TASK_ID}} ($subject) finished with exit code $exitcode"
exit $exitcode
