from neuro_workflow.analysis.lev1.processing.fixed_effects import FixedEffectsAnalyzer


def test_rtmodel_tag_switches_with_no_rt():
    a = FixedEffectsAnalyzer(
        "sub-s10", "cuedTS", hemisphere="L", surface_space="fsaverage6", no_rt=True
    )
    # _build_base_filename reads self.contrast_results[contrast_name]["n_runs"]
    # to decide the belowMinRuns tag; populate it directly since we're testing
    # the filename builder in isolation, not the full compute pipeline.
    a.contrast_results["cti-tsr"] = {"n_runs": 3}
    fn = a._build_base_filename("cti-tsr")
    assert "_rtmodel-noRT_" in fn and "RTDur" not in fn

    b = FixedEffectsAnalyzer("sub-s10", "cuedTS", hemisphere="L", surface_space="fsaverage6")
    b.contrast_results["cti-tsr"] = {"n_runs": 3}
    assert "_rtmodel-RTDur_" in b._build_base_filename("cti-tsr")
