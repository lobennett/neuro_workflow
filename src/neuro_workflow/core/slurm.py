import subprocess
import sys
import tempfile
from pathlib import Path


def count_subjects(subjects_file):
    with open(subjects_file) as f:
        return sum(1 for line in f if line.strip())


def load_subjects(subjects_file):
    with open(subjects_file) as f:
        return [line.strip() for line in f if line.strip()]


def render_template(template_path, context):
    template = Path(template_path).read_text()
    return template.format(**context)


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
