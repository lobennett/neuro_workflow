#!/bin/bash
#SBATCH -J qsiprep_{dataset_name}
#SBATCH --time={time}
#SBATCH -n 1
#SBATCH --array=1-{n_subjects}
#SBATCH --cpus-per-task={nthreads}
#SBATCH --mem-per-cpu={mem_per_cpu_gb}G
#SBATCH -p {partition}
#SBATCH -o {log_dir}/%x-%A-%a.out
#SBATCH -e {log_dir}/%x-%A-%a.err
{mail_line}

subject=$(sed "${{SLURM_ARRAY_TASK_ID}}q;d" {subjects_file})

QSIPREP_IMG="{image_path}"

mkdir -p "{work_dir}"

apptainer run --cleanenv \
  -B {bids_dir}:/data \
  -B {work_dir}:/work \
  -B {fs_license}:/opt/freesurfer/license.txt \
  "$QSIPREP_IMG" \
  /data /data/derivatives/qsiprep_{qsiprep_version} participant \
  --participant-label "$subject" \
  -w /work \
  --nthreads {nthreads} \
  --mem-mb {mem_mb} \
  --output-resolution {output_resolution} \
  {qsiprep_args}

exitcode=$?
echo "Task ${{SLURM_ARRAY_TASK_ID}} ($subject) finished with exit code $exitcode"
exit $exitcode
