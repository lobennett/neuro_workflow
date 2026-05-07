"""Fixed effects analysis for combining results across runs."""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

import numpy as np
from nilearn.glm.contrasts import compute_fixed_effects
from nilearn.image import load_img

from neuro_workflow.analysis.lev1.processing.surface_data import (
    compute_surface_fixed_effects,
    SurfaceResult,
)
from neuro_workflow.analysis.task_config.loader import get_task_contrasts

logger = logging.getLogger(__name__)


class FixedEffectsAnalyzer:
    """Analyzer for computing fixed effects across runs."""

    def __init__(
        self,
        subject_id: str,
        task_name: str,
        mask_img: Optional[Union[str, Path]] = None,
        high_exclusion: bool = False,
        hemisphere: Optional[str] = None,
        surface_space: str = 'fsnative',
    ):
        """Initialize fixed effects analyzer.

        Args:
            subject_id: Subject identifier
            task_name: Task name
            mask_img: Optional brain mask image
            high_exclusion: Whether >50% of runs were excluded
            hemisphere: Optional hemisphere ('L' or 'R') for surface data
            surface_space: Surface space name for output filenames (default 'fsnative')

        Examples:
            >>> analyzer = FixedEffectsAnalyzer('sub-01', 'stopSignal')
            >>> analyzer_L = FixedEffectsAnalyzer('sub-01', 'stopSignal', hemisphere='L')
        """
        self.subject_id = subject_id
        self.task_name = task_name
        self.mask_img = mask_img
        self.high_exclusion = high_exclusion
        self.hemisphere = hemisphere
        self.surface_space = surface_space
        self.contrast_results = {}

    def find_contrast_files(
        self,
        contrast_dir: Path,
        contrast_name: str,
        exclusions: Optional[Set[str]] = None,
    ) -> Tuple[List[Path], List[Path]]:
        """Find effect size and variance files for a contrast.

        Args:
            contrast_dir: Directory containing contrast files
            contrast_name: Name of the contrast
            exclusions: Set of exclusion keys to skip

        Returns:
            Tuple of (effect_files, variance_files)

        Examples:
            >>> effects, variances = analyzer.find_contrast_files(
            ...     Path('./contrasts'), 'inhibition', {'sub-01_ses-01_task-stop_run-1'}
            ... )
        """
        if exclusions is None:
            exclusions = set()

        # Determine file extension based on hemisphere (surface vs volumetric)
        if self.hemisphere is not None:
            file_ext = '.func.gii'
            # Pattern for surface files: match hemi-L_ or hemi-R_ followed by contrast
            effect_pattern = f'*hemi-{self.hemisphere}_*contrast-{contrast_name}*stat-effect-size{file_ext}'
            variance_pattern = f'*hemi-{self.hemisphere}_*contrast-{contrast_name}*stat-variance{file_ext}'
        else:
            file_ext = '.nii.gz'
            # Pattern for volumetric files
            effect_pattern = f'*contrast-{contrast_name}*stat-effect-size{file_ext}'
            variance_pattern = f'*contrast-{contrast_name}*stat-variance{file_ext}'

        effect_files = []
        variance_files = []

        # Find all matching files
        all_effect_files = list(contrast_dir.glob(effect_pattern))
        all_variance_files = list(contrast_dir.glob(variance_pattern))

        # Filter out excluded runs
        for effect_file in all_effect_files:
            # Parse filename to check for exclusions
            exclusion_key = self._parse_exclusion_key(effect_file)
            if exclusion_key not in exclusions:
                effect_files.append(effect_file)

                # Find corresponding variance file
                variance_file = effect_file.with_name(
                    effect_file.name.replace('stat-effect-size', 'stat-variance')
                )
                if variance_file in all_variance_files:
                    variance_files.append(variance_file)
                else:
                    logger.warning('Missing variance file for %s', effect_file)

        # Sort files to ensure consistent ordering
        effect_files.sort()
        variance_files.sort()

        return effect_files, variance_files

    def _parse_exclusion_key(self, filepath: Path) -> str:
        """Parse exclusion key from contrast filename.

        The key format must match what run_lev1.py uses:
            '{subject}_{session}_task-{task_name}_{run}'

        Args:
            filepath: Path to contrast file

        Returns:
            Exclusion key in format 'sub-X_ses-Y_task-TASK_run-Z'

        Examples:
            >>> key = analyzer._parse_exclusion_key(
            ...     Path('sub-s03_ses-01_task-stopSignal_run-01_contrast-go.nii.gz')
            ... )
            >>> key
            'sub-s03_ses-01_task-stopSignal_run-1'
        """
        filename = filepath.name

        # Use [^_]+ (non-underscore) to avoid over-matching across BIDS entities
        patterns = {
            'subject': r'(sub-[^_]+)',
            'session': r'(ses-[^_]+)',
            'run': r'run-(\d+)',
        }

        components = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, filename)
            if match:
                if key == 'run':
                    run_num = match.group(1).lstrip('0') or '0'
                    components[key] = f'run-{run_num}'
                else:
                    components[key] = match.group(1)

        # Create exclusion key with task- prefix (matching run_lev1.py format)
        if all(k in components for k in ['subject', 'session', 'run']):
            return f'{components["subject"]}_{components["session"]}_task-{self.task_name}_{components["run"]}'

        return filename  # Fallback to filename if parsing fails

    def compute_fixed_effects_contrast(
        self,
        contrast_name: str,
        effect_files: List[Path],
        variance_files: List[Path],
        precision_weighted: bool = False,
    ) -> Tuple[Optional[any], Optional[any], Optional[any]]:
        """Compute fixed effects for a single contrast.

        Args:
            contrast_name: Name of the contrast
            effect_files: List of effect size image files
            variance_files: List of variance image files
            precision_weighted: Whether to use precision weighting

        Returns:
            Tuple of (fixed_effect_img, fixed_variance_img, fixed_stat_img)

        Examples:
            >>> effect_img, var_img, stat_img = analyzer.compute_fixed_effects_contrast(
            ...     'inhibition', effect_files, variance_files
            ... )
        """
        if len(effect_files) != len(variance_files):
            logger.error(
                'File count mismatch for %s: %d effects, %d variances',
                contrast_name, len(effect_files), len(variance_files),
            )
            return None, None, None

        if not effect_files:
            logger.warning('No files found for contrast %s', contrast_name)
            return None, None, None

        try:
            # Use surface-specific fixed effects for GIFTI files
            if self.hemisphere is not None:
                # Surface data - use custom implementation
                fixed_effect_result, fixed_variance_result, fixed_stat_result = (
                    compute_surface_fixed_effects(
                        effect_files,
                        variance_files,
                        precision_weighted=precision_weighted,
                    )
                )
                # These are SurfaceResult objects, store them directly
                fixed_effect_img = fixed_effect_result
                fixed_variance_img = fixed_variance_result
                fixed_stat_img = fixed_stat_result
            else:
                # Volumetric data - use nilearn's implementation.
                # nilearn >=0.10 returns 4 values: (effect, variance, stat, z_score).
                # We only consume the first three (matches the surface path's 3-tuple).
                _result = compute_fixed_effects(
                    effect_files,
                    variance_files,
                    mask=self.mask_img,
                    precision_weighted=precision_weighted,
                )
                fixed_effect_img, fixed_variance_img, fixed_stat_img = _result[:3]

            logger.info('Fixed effects for %s: %d runs included', contrast_name, len(effect_files))

            # Store results
            self.contrast_results[contrast_name] = {
                'fixed_effect': fixed_effect_img,
                'fixed_variance': fixed_variance_img,
                'fixed_stat': fixed_stat_img,
                'n_runs': len(effect_files),
                'input_files': {'effects': effect_files, 'variances': variance_files},
            }

            return fixed_effect_img, fixed_variance_img, fixed_stat_img

        except Exception as e:
            logger.error('Fixed effects failed for %s: %s', contrast_name, e)
            return None, None, None

    def save_fixed_effects_maps(
        self, contrast_name: str, output_dir: Path, base_filename: Optional[str] = None
    ) -> Dict[str, Path]:
        """Save fixed effects maps for a contrast.

        Args:
            contrast_name: Name of the contrast
            output_dir: Directory to save maps
            base_filename: Optional base filename

        Returns:
            Dictionary mapping map types to saved paths

        Examples:
            >>> saved_files = analyzer.save_fixed_effects_maps(
            ...     'inhibition', Path('./fixed_effects')
            ... )
        """
        if contrast_name not in self.contrast_results:
            raise ValueError(
                f'Fixed effects for {contrast_name} have not been computed'
            )

        results = self.contrast_results[contrast_name]
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Determine file extension and hemisphere tag
        if self.hemisphere is not None:
            file_ext = '.func.gii'
            hemi_tag = f'_hemi-{self.hemisphere}'
            space_tag = f'_space-{self.surface_space}'
        else:
            file_ext = '.nii.gz'
            hemi_tag = ''
            space_tag = ''

        if base_filename is None:
            high_excl_tag = '_desc-highExclusion' if self.high_exclusion else ''
            base_filename = f'{self.subject_id}{hemi_tag}{space_tag}_task-{self.task_name}_contrast-{contrast_name}_rtmodel-RTDur{high_excl_tag}_stat-fixed-effects'

        saved_files = {}

        # Save fixed effects maps
        if results['fixed_effect'] is not None:
            effect_path = output_dir / f'{base_filename}{file_ext}'
            results['fixed_effect'].to_filename(effect_path)
            saved_files['fixed_effect'] = effect_path

        if results['fixed_variance'] is not None:
            variance_path = output_dir / f'{base_filename}-variance{file_ext}'
            results['fixed_variance'].to_filename(variance_path)
            saved_files['fixed_variance'] = variance_path

        if results['fixed_stat'] is not None:
            stat_path = output_dir / f'{base_filename}-z_score{file_ext}'
            results['fixed_stat'].to_filename(stat_path)
            saved_files['fixed_stat'] = stat_path

        return saved_files

    def compute_all_task_fixed_effects(
        self,
        contrast_dir: Path,
        output_dir: Path,
        exclusions: Optional[Set[str]] = None,
        contrasts: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Dict[str, Path]]:
        """Compute fixed effects for all task contrasts.

        Args:
            contrast_dir: Directory containing individual contrast files
            output_dir: Directory to save fixed effects results
            exclusions: Set of runs to exclude
            contrasts: Optional custom contrasts dictionary

        Returns:
            Dictionary mapping contrast names to saved file paths

        Examples:
            >>> results = analyzer.compute_all_task_fixed_effects(
            ...     Path('./contrasts'), Path('./fixed_effects'), exclusions
            ... )
        """
        if contrasts is None:
            contrasts = get_task_contrasts(self.task_name)

        all_saved_files = {}

        for contrast_name in contrasts.keys():
            # Find files for this contrast
            effect_files, variance_files = self.find_contrast_files(
                contrast_dir, contrast_name, exclusions
            )

            if effect_files and variance_files:
                # Compute fixed effects
                fixed_effect, fixed_variance, fixed_stat = (
                    self.compute_fixed_effects_contrast(
                        contrast_name, effect_files, variance_files
                    )
                )

                if fixed_effect is not None:
                    # Save results
                    saved_files = self.save_fixed_effects_maps(
                        contrast_name, output_dir
                    )
                    all_saved_files[contrast_name] = saved_files

        return all_saved_files

    def get_contrast_summary(self) -> Dict[str, Dict]:
        """Get summary of computed fixed effects contrasts.

        Returns:
            Dictionary with contrast summaries

        Examples:
            >>> summary = analyzer.get_contrast_summary()
        """
        summary = {}

        for contrast_name, results in self.contrast_results.items():
            summary[contrast_name] = {
                'n_runs_included': results['n_runs'],
                'has_fixed_effect': results['fixed_effect'] is not None,
                'has_fixed_variance': results['fixed_variance'] is not None,
                'has_fixed_stat': results['fixed_stat'] is not None,
                'input_files': {
                    'n_effect_files': len(results['input_files']['effects']),
                    'n_variance_files': len(results['input_files']['variances']),
                },
            }

        return summary


def compute_subject_fixed_effects(
    subject_id: str,
    task_name: str,
    contrast_dir: Path,
    output_dir: Path,
    mask_img: Optional[Union[str, Path]] = None,
    exclusions: Optional[Set[str]] = None,
    high_exclusion: bool = False,
    hemisphere: Optional[str] = None,
    surface_space: str = 'fsnative',
) -> Dict[str, Dict[str, Path]]:
    """Compute fixed effects for all contrasts for a subject.

    Args:
        subject_id: Subject identifier
        task_name: Task name
        contrast_dir: Directory with individual contrast files
        output_dir: Directory to save fixed effects
        mask_img: Optional brain mask
        exclusions: Optional set of runs to exclude
        high_exclusion: Whether >50% of runs were excluded
        hemisphere: Optional hemisphere ('L' or 'R') for surface data
        surface_space: Surface space name for output filenames (default 'fsnative')

    Returns:
        Dictionary mapping contrast names to saved file paths

    Examples:
        >>> results = compute_subject_fixed_effects(
        ...     'sub-01', 'stopSignal', Path('./contrasts'), Path('./fixed_effects')
        ... )
        >>> results_L = compute_subject_fixed_effects(
        ...     'sub-01', 'stopSignal', Path('./contrasts'), Path('./fixed_effects'),
        ...     hemisphere='L'
        ... )
    """
    analyzer = FixedEffectsAnalyzer(
        subject_id, task_name, mask_img, high_exclusion, hemisphere,
        surface_space=surface_space,
    )

    return analyzer.compute_all_task_fixed_effects(contrast_dir, output_dir, exclusions)
