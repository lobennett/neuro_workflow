import os
from pathlib import Path
from fmriprep_workflow.submit import render_sbatch, count_subjects


def test_count_subjects(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\ns10\ns19\n")
    assert count_subjects(str(subs)) == 3


def test_count_subjects_ignores_blank_lines(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n\ns10\n\n")
    assert count_subjects(str(subs)) == 2


def test_render_sbatch_basic(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\ns10\n")

    config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "fmriprep_version": "24.1.0",
        "output_spaces": "MNI152NLin2009cAsym:res-2 fsnative",
        "fmriprep_args": "--no-submm-recon",
        "partition": "russpold",
        "nthreads": 8,
        "mem_per_cpu_gb": 8,
        "time": "5-00:00:00",
        "image_dir": "/images",
        "templateflow_dir": "/home/groups/russpold/templateflow",
        "fs_license": "/home/user/license.txt",
        "bids_filter_file": None,
        "mail_user": None,
    }

    script = render_sbatch("test_ds", config)

    assert "#SBATCH -J fmriprep_test_ds" in script
    assert "#SBATCH --array=1-2" in script
    assert "--participant-label \"$subject\"" in script
    assert "/images/fmriprep_24.1.0.sif" in script
    assert "--no-submm-recon" in script
    assert "--output-spaces MNI152NLin2009cAsym:res-2 fsnative" in script
    # No mail line when mail_user is None
    assert "--mail-user" not in script


def test_render_sbatch_with_mail(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "fmriprep_version": "24.1.0",
        "output_spaces": "MNI152NLin2009cAsym:res-2",
        "fmriprep_args": "",
        "partition": "russpold",
        "nthreads": 8,
        "mem_per_cpu_gb": 8,
        "time": "5-00:00:00",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "fs_license": "/home/user/license.txt",
        "bids_filter_file": None,
        "mail_user": "user@stanford.edu",
    }

    script = render_sbatch("test_ds", config)
    assert "#SBATCH --mail-user=user@stanford.edu" in script
    assert "#SBATCH --mail-type=ALL" in script


def test_render_sbatch_with_bids_filter(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "fmriprep_version": "24.1.0",
        "output_spaces": "MNI152NLin2009cAsym:res-2",
        "fmriprep_args": "",
        "partition": "russpold",
        "nthreads": 8,
        "mem_per_cpu_gb": 8,
        "time": "5-00:00:00",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "fs_license": "/home/user/license.txt",
        "bids_filter_file": "/home/user/filter.json",
        "mail_user": None,
    }

    script = render_sbatch("test_ds", config)
    assert "-B /home/user:/config" in script
    assert "--bids-filter-file /config/filter.json" in script


def test_render_sbatch_mem_mb_is_90_percent(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "fmriprep_version": "24.1.0",
        "output_spaces": "MNI152NLin2009cAsym:res-2",
        "fmriprep_args": "",
        "partition": "russpold",
        "nthreads": 8,
        "mem_per_cpu_gb": 8,
        "time": "5-00:00:00",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "fs_license": "/home/user/license.txt",
        "bids_filter_file": None,
        "mail_user": None,
    }

    script = render_sbatch("test_ds", config)
    # 8 threads * 8 GB * 1000 * 0.9 = 57600
    assert "--mem_mb 57600" in script
