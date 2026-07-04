"""Tests for physio CSV-to-BIDS conversion."""

import gzip
import json

from neuro_workflow.bidsify.physio import (
    build_trigger_column,
    convert_physio_to_bids,
    parse_flt_data,
    parse_flt_trig,
)


class TestParseFltData:
    def test_parse_basic(self, tmp_path):
        """Parse PPG_FltData.csv: timestamp_ms,amplitude rows."""
        csv_path = tmp_path / "PPG_FltData.csv"
        csv_path.write_text("10,0.453789\n20,0.445052\n30,0.436389\n")

        timestamps, amplitudes = parse_flt_data(csv_path)

        assert timestamps == [10, 20, 30]
        assert len(amplitudes) == 3
        assert abs(amplitudes[0] - 0.453789) < 1e-6

    def test_parse_empty(self, tmp_path):
        """Empty file returns empty lists."""
        csv_path = tmp_path / "PPG_FltData.csv"
        csv_path.write_text("")

        timestamps, amplitudes = parse_flt_data(csv_path)

        assert timestamps == []
        assert amplitudes == []


class TestParseFltTrig:
    def test_parse_triggers(self, tmp_path):
        """Parse PPG_FltTrig.csv: one timestamp per line."""
        trig_path = tmp_path / "PPG_FltTrig.csv"
        trig_path.write_text("440\n1230\n2040\n")

        triggers = parse_flt_trig(trig_path)

        assert triggers == [440, 1230, 2040]

    def test_parse_empty_triggers(self, tmp_path):
        """Empty trigger file returns empty list."""
        trig_path = tmp_path / "PPG_FltTrig.csv"
        trig_path.write_text("")

        triggers = parse_flt_trig(trig_path)

        assert triggers == []


class TestBuildTriggerColumn:
    def test_trigger_at_matching_timestamps(self):
        """Trigger column is 1 at matching timestamps, 0 elsewhere."""
        timestamps = [10, 20, 30, 40, 50]
        trigger_times = [20, 40]

        result = build_trigger_column(timestamps, trigger_times)

        assert result == [0, 1, 0, 1, 0]

    def test_no_triggers(self):
        """All zeros when no trigger times."""
        timestamps = [10, 20, 30]
        trigger_times = []

        result = build_trigger_column(timestamps, trigger_times)

        assert result == [0, 0, 0]


class TestConvertPhysioToBids:
    def test_converts_cardiac(self, tmp_path):
        """Full cardiac conversion: CSV -> tsv.gz + JSON sidecar."""
        # Create input CSVs
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "PPG_FltData.csv").write_text("10,0.40\n20,0.45\n30,0.50\n40,0.55\n50,0.60\n")
        (input_dir / "PPG_FltTrig.csv").write_text("20\n40\n")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        convert_physio_to_bids(
            input_dir=input_dir,
            output_dir=output_dir,
            subject="s1175",
            session="ses-02",
            task="rest",
            run=1,
            channel="cardiac",
        )

        # Check TSV
        tsv_path = output_dir / "sub-s1175_ses-02_task-rest_run-1_recording-cardiac_physio.tsv.gz"
        assert tsv_path.exists()
        content = gzip.decompress(tsv_path.read_bytes()).decode()
        lines = content.strip().split("\n")
        assert lines[0] == "cardiac\ttrigger"
        parts = lines[1].split("\t")
        assert float(parts[0]) == 0.40 and parts[1] == "0"
        parts = lines[2].split("\t")
        assert float(parts[0]) == 0.45 and parts[1] == "1"  # trigger at timestamp 20

        # Check JSON
        json_path = output_dir / "sub-s1175_ses-02_task-rest_run-1_recording-cardiac_physio.json"
        assert json_path.exists()
        meta = json.loads(json_path.read_text())
        assert meta["SamplingFrequency"] == 100
        assert meta["StartTime"] == 0.0
        assert meta["Columns"] == ["cardiac", "trigger"]

    def test_converts_respiratory(self, tmp_path):
        """Full respiratory conversion: CSV -> tsv.gz + JSON sidecar."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "RESP_FltData.csv").write_text("40,0.73\n80,0.74\n120,0.75\n")
        (input_dir / "RESP_FltTrig.csv").write_text("80\n")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        convert_physio_to_bids(
            input_dir=input_dir,
            output_dir=output_dir,
            subject="s1175",
            session="ses-02",
            task="rest",
            run=1,
            channel="respiratory",
        )

        tsv_path = (
            output_dir / "sub-s1175_ses-02_task-rest_run-1_recording-respiratory_physio.tsv.gz"
        )
        assert tsv_path.exists()
        content = gzip.decompress(tsv_path.read_bytes()).decode()
        lines = content.strip().split("\n")
        assert lines[0] == "respiratory\ttrigger"
        parts = lines[2].split("\t")
        assert float(parts[0]) == 0.74 and parts[1] == "1"  # trigger at timestamp 80

        json_path = (
            output_dir / "sub-s1175_ses-02_task-rest_run-1_recording-respiratory_physio.json"
        )
        meta = json.loads(json_path.read_text())
        assert meta["SamplingFrequency"] == 25

    def test_converts_with_missing_trigger_file(self, tmp_path):
        """Full conversion works even if trigger file is missing."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "PPG_FltData.csv").write_text("10,0.40\n20,0.45\n30,0.50\n")
        # No PPG_FltTrig.csv created

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = convert_physio_to_bids(
            input_dir=input_dir,
            output_dir=output_dir,
            subject="s1175",
            session="ses-02",
            task="rest",
            run=1,
            channel="cardiac",
        )

        assert result is True
        tsv_path = output_dir / "sub-s1175_ses-02_task-rest_run-1_recording-cardiac_physio.tsv.gz"
        content = gzip.decompress(tsv_path.read_bytes()).decode()
        lines = content.strip().split("\n")
        # All trigger values should be 0 since no trigger file exists
        assert all(line.endswith("\t0") for line in lines[1:])

    def test_skips_missing_data_file(self, tmp_path):
        """Returns False when data CSV is missing."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = convert_physio_to_bids(
            input_dir=input_dir,
            output_dir=output_dir,
            subject="s1175",
            session="ses-02",
            task="rest",
            run=1,
            channel="cardiac",
        )

        assert result is False
