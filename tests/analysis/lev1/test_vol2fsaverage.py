"""Tests for MSHBM input preparation script."""

import sys
from pathlib import Path

import pytest

# Import from the consolidated helper script
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src' / 'helpers'))
from prepare_mshbm_inputs import (
    discover_rest_bold_fsaverage6,
    discover_rest_bold_surface,
    discover_rest_bold_volume,
    discover_task_residuals_surface,
    discover_task_residuals_volume,
    filter_by_sessions,
    make_output_name,
    parse_bids_entities,
)


# ---------------------------------------------------------------------------
# parse_bids_entities
# ---------------------------------------------------------------------------


class TestParseBidsEntities:
    def test_full_entities(self):
        name = 'sub-s03_ses-02_task-cuedTS_run-1_hemi-L_bold.func.gii'
        entities = parse_bids_entities(name)
        assert entities == {
            'sub': 's03',
            'ses': '02',
            'task': 'cuedTS',
            'run': '1',
            'hemi': 'L',
        }

    def test_first_match_wins(self):
        """'task-regressed' in suffix should not overwrite first task entity."""
        name = 'sub-s03_ses-01_task-nBack_run-2_task-regressed-residuals.nii.gz'
        entities = parse_bids_entities(name)
        assert entities['task'] == 'nBack'

    def test_no_session(self):
        name = 'sub-s03_task-rest_run-1_bold.nii.gz'
        entities = parse_bids_entities(name)
        assert 'ses' not in entities
        assert entities['task'] == 'rest'

    def test_no_run(self):
        name = 'sub-s03_ses-01_task-rest_bold.nii.gz'
        entities = parse_bids_entities(name)
        assert 'run' not in entities

    def test_empty_string(self):
        assert parse_bids_entities('') == {}


# ---------------------------------------------------------------------------
# filter_by_sessions
# ---------------------------------------------------------------------------


class TestFilterBySessions:
    @pytest.fixture
    def sample_files(self):
        """Create a list of Paths with various session labels."""
        return [
            Path('sub-s03_ses-01_task-cuedTS_run-1_hemi-L_residuals.func.gii'),
            Path('sub-s03_ses-01_task-cuedTS_run-1_hemi-R_residuals.func.gii'),
            Path('sub-s03_ses-02_task-nBack_run-1_hemi-L_residuals.func.gii'),
            Path('sub-s03_ses-02_task-nBack_run-1_hemi-R_residuals.func.gii'),
            Path('sub-s03_ses-03_task-flanker_run-1_hemi-L_residuals.func.gii'),
            Path('sub-s03_ses-03_task-flanker_run-1_hemi-R_residuals.func.gii'),
            Path('sub-s03_ses-05_task-goNogo_run-1_hemi-L_residuals.func.gii'),
        ]

    def test_none_returns_all(self, sample_files):
        result = filter_by_sessions(sample_files, None)
        assert result == sample_files

    def test_single_session(self, sample_files):
        result = filter_by_sessions(sample_files, {'01'})
        assert len(result) == 2
        for f in result:
            assert 'ses-01' in f.name

    def test_multiple_sessions(self, sample_files):
        result = filter_by_sessions(sample_files, {'01', '02'})
        assert len(result) == 4
        for f in result:
            entities = parse_bids_entities(f.name)
            assert entities['ses'] in {'01', '02'}

    def test_no_matching_session(self, sample_files):
        result = filter_by_sessions(sample_files, {'99'})
        assert result == []

    def test_empty_file_list(self):
        result = filter_by_sessions([], {'01', '02'})
        assert result == []

    def test_file_without_session_entity(self):
        files = [Path('sub-s03_task-rest_run-1_bold.nii.gz')]
        result = filter_by_sessions(files, {'01'})
        assert result == []

    def test_preserves_order(self, sample_files):
        result = filter_by_sessions(sample_files, {'02', '03'})
        names = [f.name for f in result]
        assert names == [
            'sub-s03_ses-02_task-nBack_run-1_hemi-L_residuals.func.gii',
            'sub-s03_ses-02_task-nBack_run-1_hemi-R_residuals.func.gii',
            'sub-s03_ses-03_task-flanker_run-1_hemi-L_residuals.func.gii',
            'sub-s03_ses-03_task-flanker_run-1_hemi-R_residuals.func.gii',
        ]


# ---------------------------------------------------------------------------
# Output naming
# ---------------------------------------------------------------------------


class TestMakeOutputName:
    def test_volume_residual(self):
        path = Path(
            'sub-s03_ses-02_task-cuedTS_run-1_task-regressed-residuals.nii.gz'
        )
        name = make_output_name(path, 'lh')
        assert name == 'lh_ses-02_task-cuedTS_run-1_nat_resid_bpss_fsaverage6_sm0.nii.gz'

    def test_surface_residual(self):
        path = Path(
            'sub-s03_ses-01_task-nBack_run-2_hemi-L_task-regressed-residuals.func.gii'
        )
        name = make_output_name(path, 'lh')
        assert name == 'lh_ses-01_task-nBack_run-2_nat_resid_bpss_fsaverage6_sm0.nii.gz'

    def test_rh(self):
        path = Path(
            'sub-s03_ses-03_task-flanker_run-1_hemi-R_task-regressed-residuals.func.gii'
        )
        name = make_output_name(path, 'rh')
        assert name == 'rh_ses-03_task-flanker_run-1_nat_resid_bpss_fsaverage6_sm0.nii.gz'

    def test_rest_volume(self):
        path = Path(
            'sub-s03_ses-01_task-rest_run-1_space-T1w_desc-preproc_bold.nii.gz'
        )
        name = make_output_name(path, 'lh')
        assert name == 'lh_ses-01_task-rest_run-1_nat_resid_bpss_fsaverage6_sm0.nii.gz'

    def test_rest_surface(self):
        path = Path(
            'sub-s03_ses-02_task-rest_run-1_hemi-L_space-fsnative_bold.func.gii'
        )
        name = make_output_name(path, 'lh')
        assert name == 'lh_ses-02_task-rest_run-1_nat_resid_bpss_fsaverage6_sm0.nii.gz'

    def test_rest_fsaverage6(self):
        path = Path(
            'sub-s03_ses-01_task-rest_run-1_hemi-L_space-fsaverage6_bold.func.gii'
        )
        name = make_output_name(path, 'lh')
        assert name == 'lh_ses-01_task-rest_run-1_nat_resid_bpss_fsaverage6_sm0.nii.gz'


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


class TestDiscoverTaskResidualsSurface:
    def test_finds_gifti_residuals(self, temp_dir):
        subj = 'sub-s03'
        task_dir = temp_dir / subj / 'task-cuedTS' / 'task_residuals'
        task_dir.mkdir(parents=True)
        gii = task_dir / 'sub-s03_ses-01_task-cuedTS_run-1_hemi-L_task-regressed-residuals.func.gii'
        gii.touch()

        result = discover_task_residuals_surface(temp_dir, subj)
        assert len(result) == 1
        assert result[0].name == gii.name

    def test_empty_when_no_dir(self, temp_dir):
        result = discover_task_residuals_surface(temp_dir, 'sub-s99')
        assert result == []


class TestDiscoverTaskResidualsVolume:
    def test_finds_nifti_residuals(self, temp_dir):
        subj = 'sub-s03'
        task_dir = temp_dir / subj / 'task-nBack' / 'task_residuals'
        task_dir.mkdir(parents=True)
        nii = task_dir / 'sub-s03_ses-02_task-nBack_run-1_task-regressed-residuals.nii.gz'
        nii.touch()

        result = discover_task_residuals_volume(temp_dir, subj)
        assert len(result) == 1
        assert result[0].name == nii.name

    def test_empty_when_no_dir(self, temp_dir):
        result = discover_task_residuals_volume(temp_dir, 'sub-s99')
        assert result == []


class TestDiscoverRestBoldSurface:
    def test_finds_fsnative_rest(self, temp_dir):
        subj = 'sub-s03'
        func_dir = temp_dir / subj / 'ses-01' / 'func'
        func_dir.mkdir(parents=True)
        gii = func_dir / 'sub-s03_ses-01_task-rest_run-1_hemi-L_space-fsnative_bold.func.gii'
        gii.touch()

        result = discover_rest_bold_surface(temp_dir, subj)
        assert len(result) == 1
        assert result[0].name == gii.name

    def test_empty_when_no_dir(self, temp_dir):
        result = discover_rest_bold_surface(temp_dir, 'sub-s99')
        assert result == []


class TestDiscoverRestBoldFsaverage6:
    def test_finds_fsaverage6_rest(self, temp_dir):
        subj = 'sub-s03'
        func_dir = temp_dir / subj / 'ses-01' / 'func'
        func_dir.mkdir(parents=True)
        gii = func_dir / 'sub-s03_ses-01_task-rest_run-1_hemi-L_space-fsaverage6_bold.func.gii'
        gii.touch()

        result = discover_rest_bold_fsaverage6(temp_dir, subj)
        assert len(result) == 1
        assert result[0].name == gii.name

    def test_empty_when_no_dir(self, temp_dir):
        result = discover_rest_bold_fsaverage6(temp_dir, 'sub-s99')
        assert result == []


class TestDiscoverRestBoldVolume:
    def test_finds_t1w_rest(self, temp_dir):
        subj = 'sub-s03'
        func_dir = temp_dir / subj / 'ses-01' / 'func'
        func_dir.mkdir(parents=True)
        nii = func_dir / 'sub-s03_ses-01_task-rest_run-1_space-T1w_desc-preproc_bold.nii.gz'
        nii.touch()

        result = discover_rest_bold_volume(temp_dir, subj)
        assert len(result) == 1
        assert result[0].name == nii.name

    def test_empty_when_no_dir(self, temp_dir):
        result = discover_rest_bold_volume(temp_dir, 'sub-s99')
        assert result == []


# ---------------------------------------------------------------------------
# Integration: discovery + session filter
# ---------------------------------------------------------------------------


class TestDiscoveryWithSessionFilter:
    def test_surface_residuals_filtered_to_sessions(self, temp_dir):
        """End-to-end: discover surface residuals then filter to ses-01/02."""
        subj = 'sub-s03'
        for ses in ['01', '02', '03']:
            for task in ['cuedTS', 'nBack']:
                task_dir = temp_dir / subj / f'task-{task}' / 'task_residuals'
                task_dir.mkdir(parents=True, exist_ok=True)
                for hemi in ['L', 'R']:
                    gii = task_dir / (
                        f'sub-s03_ses-{ses}_task-{task}_run-1_hemi-{hemi}'
                        '_task-regressed-residuals.func.gii'
                    )
                    gii.touch()

        files = discover_task_residuals_surface(temp_dir, subj)
        assert len(files) == 12  # 3 sessions * 2 tasks * 2 hemis

        filtered = filter_by_sessions(files, {'01', '02'})
        assert len(filtered) == 8  # 2 sessions * 2 tasks * 2 hemis
        for f in filtered:
            entities = parse_bids_entities(f.name)
            assert entities['ses'] in {'01', '02'}

    def test_rest_surface_filtered_to_sessions(self, temp_dir):
        """End-to-end: discover rest surface files then filter to ses-01."""
        subj = 'sub-s03'
        for ses in ['01', '02', '03']:
            func_dir = temp_dir / subj / f'ses-{ses}' / 'func'
            func_dir.mkdir(parents=True, exist_ok=True)
            for hemi in ['L', 'R']:
                gii = func_dir / (
                    f'sub-s03_ses-{ses}_task-rest_run-1_hemi-{hemi}'
                    '_space-fsnative_bold.func.gii'
                )
                gii.touch()

        files = discover_rest_bold_surface(temp_dir, subj)
        assert len(files) == 6  # 3 sessions * 2 hemis

        filtered = filter_by_sessions(files, {'01'})
        assert len(filtered) == 2  # 1 session * 2 hemis
        for f in filtered:
            assert 'ses-01' in f.name
