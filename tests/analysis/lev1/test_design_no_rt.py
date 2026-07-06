from neuro_workflow.analysis.lev1.processing import design


def test_no_rt_removes_response_time_from_config(monkeypatch):
    fake_cfg = {
        "task": {"amplitude": 1, "duration": 0},
        "response_time": {"amplitude": 1, "duration": "response_time"},
    }
    monkeypatch.setattr(design, "get_regressor_config", lambda _t: dict(fake_cfg))

    seen = {}

    def fake_create_regressor(events, cfg, n, name, tr):
        seen[name] = cfg
        import numpy as np
        import pandas as pd

        return pd.DataFrame({name: np.zeros(n)}), []

    monkeypatch.setattr(design, "create_regressor", fake_create_regressor)

    import pandas as pd

    ev = pd.DataFrame(
        {
            "onset": [0.0],
            "duration": [1.0],
            "trial_type": ["test_trial"],
            "response_time": [0.5],
        }
    )
    confounds = pd.DataFrame(index=range(10))
    design.create_design_matrix(ev, confounds, n_scans=10, task_name="cuedTS", tr=1.0, no_rt=True)
    assert "response_time" not in seen and "task" in seen
