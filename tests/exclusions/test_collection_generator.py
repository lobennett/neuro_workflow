"""J1: the collection generator folds the committed collection .bidsignore
func-BOLD exclusions into the compiled set (expanded per scan via BIDS glob),
skipping anat/wildcard lines and deduping echoes.
"""

from argparse import Namespace

import neuro_workflow.core.exclusions_render as render_mod
import neuro_workflow.exclusions.collection as coll


def _mk_multiecho(bids, sub, ses, task, run):
    d = bids / sub / ses / "func"
    d.mkdir(parents=True, exist_ok=True)
    for e in (1, 2, 3):
        (d / f"{sub}_{ses}_task-{task}_run-{run}_echo-{e}_bold.nii.gz").write_bytes(b"")


def test_collection_generator_expands_func_skips_anat_dedups_echoes(tmp_path, monkeypatch):
    coll_dir = tmp_path / "data"
    coll_dir.mkdir()
    (coll_dir / "testds_collection.bidsignore").write_text(
        "# Human-curated header\n"
        "# Legacy anat — skipped\n"
        "sub-*/ses-*/anat/*acq-MPRAGEPromo_run-1_T1w.*\n"
        "sub-s03/ses-05/anat/*SagMPRAGE*\n"
        "# s03 ses-01 nBack: missing behavioral\n"
        "sub-s03/ses-01/func/sub-s03_ses-01_task-nBack_run-*_echo-*_bold.*\n"
        "# s10 ses-01 goNogo run-1: premature\n"
        "sub-s10/ses-01/func/sub-s10_ses-01_task-goNogo_run-1_echo-*_bold.*\n"
    )
    monkeypatch.setattr(render_mod, "_COLLECTION_DIR", coll_dir)
    monkeypatch.setattr(coll, "load_dataset_subjects", lambda ds: {"sub-s03", "sub-s10"})

    bids = tmp_path / "bids"
    _mk_multiecho(bids, "sub-s03", "ses-01", "nBack", "1")
    _mk_multiecho(bids, "sub-s03", "ses-01", "nBack", "2")  # run-* should catch both
    _mk_multiecho(bids, "sub-s10", "ses-01", "goNogo", "1")
    _mk_multiecho(bids, "sub-s10", "ses-01", "goNogo", "2")  # run-1 line must NOT catch this

    entries = coll.CollectionGenerator().generate("testds", {"bids_dir": str(bids)}, Namespace())
    keys = {(e["subject"], e["session"], e["task"], e["run"]) for e in entries}

    assert ("sub-s03", "ses-01", "task-nBack", "run-1") in keys
    assert ("sub-s03", "ses-01", "task-nBack", "run-2") in keys  # run-* expansion
    assert ("sub-s10", "ses-01", "task-goNogo", "run-1") in keys
    assert ("sub-s10", "ses-01", "task-goNogo", "run-2") not in keys  # run-1 line only
    assert len(entries) == 3, entries  # no echo duplicates, no anat lines
    assert all(e["source"] == "collection" and e["action"] == "exclude" for e in entries)
    nback = next(e for e in entries if e["task"] == "task-nBack")
    assert "missing behavioral" in nback["reason"]  # provenance from preceding comment


def test_render_bidsignore_does_not_duplicate_collection_entries(tmp_path, monkeypatch):
    """A source=collection compiled entry must NOT add a second glob line: it is
    already present verbatim in the prepended human-curated block."""
    coll_dir = tmp_path / "data"
    coll_dir.mkdir()
    coll_line = "sub-s03/ses-01/func/sub-s03_ses-01_task-nBack_run-1_echo-*_bold.*"
    (coll_dir / "testds_collection.bidsignore").write_text(
        "# Human-curated header\n" + coll_line + "\n"
    )
    monkeypatch.setattr(render_mod, "_COLLECTION_DIR", coll_dir)

    collection_entry = {
        "subject": "sub-s03",
        "session": "ses-01",
        "task": "nBack",
        "run": "run-1",
        "source": "collection",
        "action": "exclude",
        "reason": "collection: x",
    }
    out = render_mod.render_bidsignore_with_collection("testds", [collection_entry])
    # The human line appears once; the generated section must not re-emit a
    # nBack glob for the collection entry.
    assert out.count(coll_line) == 1
    generated = out.split(coll_line, 1)[1]
    assert "task-nBack" not in generated
