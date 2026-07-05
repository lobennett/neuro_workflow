from pathlib import Path


def test_bidsify_template_binds_oak():
    tmpl = Path("src/neuro_workflow/templates/bidsify.sbatch").read_text()
    # /oak must be bound so bidsify can write BIDS output to an Oak target dir
    # (Sherlock apptainer does not guarantee an /oak auto-mount).
    assert "-B /oak:/oak" in tmpl
    assert "apptainer run" in tmpl
