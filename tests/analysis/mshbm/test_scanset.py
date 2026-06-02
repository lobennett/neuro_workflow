from neuro_workflow.analysis.mshbm.scanset import common_scan_set


def test_common_scan_set_intersects_and_reports_dropped():
    iproc = {("01", "rest", "004"), ("01", "flanker", "009"), ("02", "rest", "004")}
    xcpd = {("01", "rest", "004"), ("01", "flanker", "009")}
    fbp = {("01", "rest", "004"), ("01", "flanker", "009"), ("02", "rest", "004")}
    common, dropped = common_scan_set({"iproc": iproc, "xcpd": xcpd, "fbp": fbp})
    assert common == {("01", "rest", "004"), ("01", "flanker", "009")}
    assert dropped == {
        "xcpd": set(),
        "iproc": {("02", "rest", "004")},
        "fbp": {("02", "rest", "004")},
    }


def test_common_scan_set_empty_input():
    common, dropped = common_scan_set({})
    assert common == set()
    assert dropped == {}
