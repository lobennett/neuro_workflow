#!/bin/bash
#SBATCH -J fsqc_{dataset_name}
#SBATCH --time={time}
#SBATCH -n 1
#SBATCH --cpus-per-task={nthreads}
#SBATCH --mem-per-cpu={mem_per_cpu_gb}G
#SBATCH -p {partition}
#SBATCH -o {log_dir}/%x-%j.out
#SBATCH -e {log_dir}/%x-%j.err
{mail_line}

export SINGULARITYENV_DISPLAY=""
export SINGULARITYENV_LIBGL_ALWAYS_INDIRECT=1
export SINGULARITYENV_MESA_GL_VERSION_OVERRIDE=3.3

FSQC_IMG="{image_path}"

mkdir -p "{output_dir}"

singularity exec \
  --cleanenv \
  --writable-tmpfs \
  -B {freesurfer_dir}:/data \
  -B {output_dir}:/out \
  "$FSQC_IMG" \
  xvfb-run -a -s "-screen 0 1024x768x24 -ac +extension GLX +render -noreset" \
  /app/fsqc/run_fsqc \
  --subjects_dir /data \
  --output_dir /out \
  --subjects {subjects_list} \
  --screenshots-html \
  --surfaces-html \
  --skullstrip-html \
  --fornix-html \
  --outlier \
  {fsqc_args}

exitcode=$?
echo "FSQC finished with exit code $exitcode"
exit $exitcode
