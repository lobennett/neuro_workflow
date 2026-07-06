from neuro_workflow.analysis.task_config.loader import drop_rt_contrasts


def test_drop_rt_contrasts():
    out = drop_rt_contrasts({"cti-tsr": "task_a - task_b", "response_time": "response_time"})
    assert out == {"cti-tsr": "task_a - task_b"}
