import os
import subprocess
import sys
import tempfile
from pathlib import Path

TEMPLATE_PATH = Path(__file__).parent / "templates" / "fmriprep.sbatch"


def count_subjects(subjects_file):
    with open(subjects_file) as f:
        return sum(1 for line in f if line.strip())


def render_sbatch(dataset_name, config):
    template = TEMPLATE_PATH.read_text()

    n_subjects = count_subjects(config["subjects_file"])
    nthreads = config["nthreads"]
    mem_per_cpu_gb = config["mem_per_cpu_gb"]
    mem_mb = int(nthreads * mem_per_cpu_gb * 1000 * 0.9)

    image_path = str(Path(config["image_dir"]) / f"fmriprep_{config['fmriprep_version']}.sif")
    fs_license = str(Path(config["fs_license"]).expanduser())

    scratch = os.environ.get("SCRATCH", "/tmp")
    work_dir = f"{scratch}/work/fmriprep_{dataset_name}_{config['fmriprep_version']}"
    log_dir = f"{config['bids_dir']}/derivatives/fmriprep_{config['fmriprep_version']}/logs"

    # Mail line
    if config.get("mail_user"):
        mail_line = f"#SBATCH --mail-user={config['mail_user']}\n#SBATCH --mail-type=ALL"
    else:
        mail_line = ""

    # BIDS filter
    if config.get("bids_filter_file"):
        filter_path = Path(config["bids_filter_file"])
        config_bind_line = f"-B {filter_path.parent}:/config \\"
        bids_filter_arg = f"--bids-filter-file /config/{filter_path.name}"
    else:
        config_bind_line = ""
        bids_filter_arg = ""

    return template.format(
        dataset_name=dataset_name,
        time=config["time"],
        n_subjects=n_subjects,
        nthreads=nthreads,
        mem_per_cpu_gb=mem_per_cpu_gb,
        partition=config["partition"],
        log_dir=log_dir,
        mail_line=mail_line,
        subjects_file=config["subjects_file"],
        image_path=image_path,
        bids_dir=config["bids_dir"],
        templateflow_dir=config["templateflow_dir"],
        work_dir=work_dir,
        config_bind_line=config_bind_line,
        fmriprep_version=config["fmriprep_version"],
        mem_mb=mem_mb,
        output_spaces=config.get("output_spaces", ""),
        fs_license_container=fs_license,
        bids_filter_arg=bids_filter_arg,
        fmriprep_args=config.get("fmriprep_args", ""),
    )


def submit_sbatch(script_content):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sbatch", delete=False) as f:
        f.write(script_content)
        f.flush()
        print(f"Sbatch script written to: {f.name}")
        result = subprocess.run(["sbatch", f.name], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error submitting job: {result.stderr}", file=sys.stderr)
            sys.exit(1)
        print(result.stdout.strip())
        return result.stdout.strip()
