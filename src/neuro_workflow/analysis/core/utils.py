import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Union

logger = logging.getLogger(__name__)


def create_exclusion_key(exclusion: Dict[str, str]) -> str:
    """Create a standardized exclusion key from exclusion data.

    Args:
        exclusion: Dictionary with subject, session, task, run keys

    Returns:
        Formatted exclusion key string

    Raises:
        KeyError: If required keys are missing from exclusion
    """
    required_keys = ['subject', 'session', 'task', 'run']
    missing_keys = [key for key in required_keys if key not in exclusion]

    if missing_keys:
        raise KeyError(f'Missing required keys in exclusion: {missing_keys}')

    subj = exclusion['subject']
    ses = exclusion['session']
    task = exclusion['task']
    run = exclusion['run']
    return f'{subj}_{ses}_{task}_{run}'


def _is_flat_list_format(data) -> bool:
    """Detect whether exclusion data is the neuro_workflow flat-list format.

    neuro_workflow compiled format: a JSON list of dicts, each with a 'source' field.
    Legacy format: a JSON dict mapping type names to lists of dicts.
    """
    return isinstance(data, list)


def _load_exclusions_flat(
    data: list, exclusion_types: Optional[List[str]] = None
) -> Dict[str, Set[str]]:
    """Parse neuro_workflow compiled exclusions (flat list) into the keyed-dict format.

    Entries with action 'exclude' or 'trim' are included. Entries with
    action 'force-include' are skipped. The 'source' field becomes the key.
    """
    result: Dict[str, Set[str]] = {}
    for entry in data:
        action = entry.get('action', '')
        if action not in ('exclude', 'trim'):
            continue
        source = entry.get('source', 'unknown')
        if exclusion_types is not None and source not in exclusion_types:
            continue
        try:
            key = create_exclusion_key(entry)
            result.setdefault(source, set()).add(key)
        except KeyError as e:
            logger.warning('Skipping invalid exclusion entry: %s', e)
    for source, keys in result.items():
        logger.info('Loaded %d %s exclusions', len(keys), source)
    return result


def load_exclusions_by_type(
    exclusions_file: Union[str, Path], exclusion_types: Optional[List[str]] = None
) -> Dict[str, Set[str]]:
    """Load exclusions by type from JSON file.

    Accepts both the legacy keyed-dict format (``{"motion_exclusions": [...], ...}``)
    and the neuro_workflow compiled flat-list format (``[{"source": "motion", ...}, ...]``).

    Args:
        exclusions_file: Path to exclusions JSON file
        exclusion_types: List of exclusion types to load. If None, loads all types.

    Returns:
        Dictionary mapping exclusion type to set of exclusion keys

    Examples:
        >>> exclusions = load_exclusions_by_type('exclusions.json', ['fmriprep_exclusions'])
        >>> fmriprep_keys = exclusions['fmriprep_exclusions']
    """
    exclusions_file = Path(exclusions_file)

    if not exclusions_file.exists():
        logger.warning('Exclusions file not found: %s', exclusions_file)
        return {}

    try:
        with open(exclusions_file, 'r') as f:
            exclusions_data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning('Failed to load exclusions from %s: %s', exclusions_file, e)
        return {}

    if _is_flat_list_format(exclusions_data):
        logger.debug('Detected neuro_workflow compiled exclusions format')
        return _load_exclusions_flat(exclusions_data, exclusion_types)

    result = {}

    # If no specific types requested, load all available types
    if exclusion_types is None:
        exclusion_types = [
            key
            for key in exclusions_data.keys()
            if isinstance(exclusions_data[key], list)
        ]

    for exclusion_type in exclusion_types:
        if exclusion_type not in exclusions_data:
            logger.warning('Exclusion type "%s" not found in %s', exclusion_type, exclusions_file)
            continue

        excluded_keys = set()
        exclusions_list = exclusions_data[exclusion_type]

        if not isinstance(exclusions_list, list):
            logger.warning('Exclusion type "%s" is not a list, skipping', exclusion_type)
            continue

        for exclusion in exclusions_list:
            try:
                key = create_exclusion_key(exclusion)
                excluded_keys.add(key)
            except KeyError as e:
                logger.warning('Skipping invalid exclusion in "%s": %s', exclusion_type, e)
                continue

        result[exclusion_type] = excluded_keys
        logger.info('Loaded %d %s exclusions', len(excluded_keys), exclusion_type)

    return result


def load_exclusions(
    exclusions_file: Union[str, Path], exclusion_types: Optional[List[str]] = None
) -> Set[str]:
    """Load all exclusions from JSON file and return a combined set of exclusion keys.

    Args:
        exclusions_file: Path to exclusions JSON file
        exclusion_types: List of exclusion types to include. If None, includes all types.

    Returns:
        Set of all exclusion keys across specified types

    Examples:
        >>> # Load all exclusion types
        >>> all_exclusions = load_exclusions('exclusions.json')
        >>> # Load only fMRIPrep exclusions
        >>> fmriprep_only = load_exclusions('exclusions.json', ['fmriprep_exclusions'])
    """
    exclusions_by_type = load_exclusions_by_type(exclusions_file, exclusion_types)

    # Combine all exclusion sets
    all_exclusions = set()
    for exclusion_set in exclusions_by_type.values():
        all_exclusions.update(exclusion_set)

    total_count = len(all_exclusions)
    if total_count > 0:
        logger.info('Total exclusions loaded: %d', total_count)
        if len(all_exclusions) <= 10:  # Only show keys if reasonable number
            logger.info('Excluded keys: %s', sorted(all_exclusions))

    return all_exclusions


def check_behavioral_trim_threshold(exclusions_file: Union[str, Path], threshold: float = 0.5) -> Set[str]:
    """Check behavioral exclusions for excessive data trimming and return exclusions.

    Accepts both the legacy keyed-dict format and the neuro_workflow flat-list format.
    In the flat-list format, entries with action='trim' and a source matching 'behavioral'
    or 'neg-events' are checked.

    Args:
        exclusions_file: Path to exclusions JSON file
        threshold: Proportion threshold above which to exclude (default: 0.5 for 50%)

    Returns:
        Set of exclusion keys for scans with >threshold proportion of data trimmed
    """
    exclusions_file = Path(exclusions_file)

    if not exclusions_file.exists():
        logger.warning('Exclusions file not found: %s', exclusions_file)
        return set()

    try:
        with open(exclusions_file, 'r') as f:
            exclusions_data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning('Failed to load exclusions from %s: %s', exclusions_file, e)
        return set()

    # Determine which list of entries to check depending on format
    if _is_flat_list_format(exclusions_data):
        behavioral_sources = {'behavioral', 'neg-events', 'behavioral_exclusions'}
        candidates = [
            e for e in exclusions_data
            if e.get('action') == 'trim' and e.get('source', '') in behavioral_sources
        ]
    else:
        candidates = exclusions_data.get('behavioral_exclusions', [])

    trim_exclusions = set()
    for exclusion in candidates:
        metrics = exclusion.get('metrics', {})
        if 'total_rows' in metrics and 'rows_to_keep' in metrics:
            total_rows = metrics['total_rows']
            rows_to_keep = metrics['rows_to_keep']
            if total_rows > 0:
                proportion_kept = rows_to_keep / total_rows
                if proportion_kept < (1 - threshold):
                    try:
                        key = create_exclusion_key(exclusion)
                        trim_exclusions.add(key)
                        logger.info(
                            'Excluding %s: %d/%d rows kept (%.2f%%)',
                            key, rows_to_keep, total_rows, proportion_kept * 100,
                        )
                    except KeyError as e:
                        logger.warning('Skipping invalid exclusion with trim metrics: %s', e)

    if trim_exclusions:
        logger.info('Found %d scans with >%.0f%% data trimmed', len(trim_exclusions), threshold * 100)

    return trim_exclusions


def normalize_subject_id(subject: str) -> str:
    """Normalize subject ID by adding 'sub-' prefix if not already present.

    Args:
        subject: Subject ID string

    Returns:
        Subject ID with 'sub-' prefix
    """
    if subject.startswith('sub-'):
        return subject
    return f'sub-{subject}'
