"""provenance.fsl_version() — best-effort FSL version capture for the lev2 manifest."""

from neuro_workflow.core import provenance


def test_fsl_version_unknown_without_fsldir(monkeypatch):
    monkeypatch.delenv("FSLDIR", raising=False)
    assert provenance.fsl_version() == "unknown"


def test_fsl_version_reads_version_file(tmp_path, monkeypatch):
    fsldir = tmp_path / "fsl"
    (fsldir / "etc").mkdir(parents=True)
    (fsldir / "etc" / "fslversion").write_text("6.0.7.4:abcdef\n")
    monkeypatch.setenv("FSLDIR", str(fsldir))
    # Takes the version, stripping the trailing build-hash field after ':'.
    assert provenance.fsl_version() == "6.0.7.4"


def test_fsl_version_unknown_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("FSLDIR", str(tmp_path / "nope"))
    assert provenance.fsl_version() == "unknown"
