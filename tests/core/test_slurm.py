from neuro_workflow.core.slurm import count_subjects, load_subjects, render_template


def test_count_subjects(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\ns10\ns19\n")
    assert count_subjects(str(subs)) == 3


def test_count_subjects_ignores_blank_lines(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n\ns10\n\n")
    assert count_subjects(str(subs)) == 2


def test_load_subjects(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\ns10\n\ns19\n")
    assert load_subjects(str(subs)) == ["s03", "s10", "s19"]


def test_render_template(tmp_path):
    template = tmp_path / "test.sbatch"
    template.write_text("#!/bin/bash\n#SBATCH -J {job_name}\necho {greeting}")
    result = render_template(template, {"job_name": "test_job", "greeting": "hello"})
    assert "test_job" in result
    assert "hello" in result


def test_render_template_from_path_object(tmp_path):
    template = tmp_path / "test.sbatch"
    template.write_text("#!/bin/bash\n#SBATCH -J {name}\n")
    result = render_template(template, {"name": "mytest"})
    assert "#SBATCH -J mytest" in result
