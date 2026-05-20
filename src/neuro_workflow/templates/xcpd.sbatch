#!/bin/bash
#SBATCH -J xcpd_{dataset_name}
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

XCPD_IMG="{image_path}"

mkdir -p "{log_dir}"
mkdir -p "{work_dir}/sub-${{subject}}"
mkdir -p "{output_dir}/sub-${{subject}}"

apptainer run --cleanenv \
  -B {fmriprep_dir}:/data:ro \
  -B {output_dir}:/out \
  -B {work_dir}:/work \
  -B {fs_license}:/opt/freesurfer/license.txt \
  "$XCPD_IMG" \
  /data /out participant \
  --participant-label "$subject" \
  -w /work/sub-${{subject}} \
  --mode abcd \
  --despike \
  --fd-thresh 0.3 \
  --input-type fmriprep \
  --warp-surfaces-native2std \
  --combine-runs \
  --linc-qc \
  --min-time 150 \
  --min-coverage 0.5 \
  --band-stop-min 12 --band-stop-max 20 --motion-filter-type notch \
  --omp-nthreads 3 \
  --nprocs {nthreads} \
  --smoothing 0 \
  --motion-filter-order 4 \
  {xcpd_args} \
  -vv

exitcode=$?
echo "Task ${{SLURM_ARRAY_TASK_ID}} ($subject) finished with exit code $exitcode"
exit $exitcode
