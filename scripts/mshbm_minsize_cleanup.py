"""Clean up small clusters in MSHBM fsaverage6 dlabel.nii outputs.

Reads a dlabel CIFTI (81924 cortical grayordinates, 40962 L + 40962 R),
applies Godfrey-style min-size cluster reassignment per hemisphere using
templateflow fsaverage6 surface topology, and writes a sibling output
with a BIDS-friendly suffix:

  sub-{XXX}_MSHBM.dlabel.nii  →  sub-{XXX}_MSHBM_minsize-{N}.dlabel.nii

The original CIFTI label table (network names + colors) is preserved.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import nibabel as nib
import numpy as np

from neuro_workflow.analysis.mshbm.minsize import (
    build_neighbors_from_faces,
    cleanup_small_clusters,
    fsaverage6_pial_path,
)

logger = logging.getLogger(__name__)

# Module-level cache: building neighbors from 81920 faces takes ~10s
_NEIGHBOR_CACHE: dict[str, list[set[int]]] = {}


def get_neighbors(hemi: str) -> list[set[int]]:
    if hemi in _NEIGHBOR_CACHE:
        return _NEIGHBOR_CACHE[hemi]
    pial = fsaverage6_pial_path(hemi)
    if not pial.is_file():
        raise FileNotFoundError(f'fsaverage6 pial not found at {pial}')
    g = nib.load(str(pial))
    faces = g.darrays[1].data
    nv = g.darrays[0].data.shape[0]
    logger.info('Building neighbor graph for hemi-%s (%d verts, %d faces)',
                hemi, nv, faces.shape[0])
    nb = build_neighbors_from_faces(faces, n_vertices=nv)
    _NEIGHBOR_CACHE[hemi] = nb
    return nb


def cleanup_dlabel(in_path: Path, out_path: Path, min_size: int) -> None:
    img = nib.load(str(in_path))
    data = np.asarray(img.get_fdata()).astype(np.int64)
    if data.shape != (1, 81924):
        raise ValueError(
            f'Expected dlabel shape (1, 81924) for fsaverage6 cortex; got {data.shape}'
        )
    labels = data[0].copy()
    lh = labels[:40962]
    rh = labels[40962:]

    nb_l = get_neighbors('L')
    nb_r = get_neighbors('R')

    logger.info('cleaning lh (%d verts, %d non-background)',
                lh.size, int((lh != 0).sum()))
    lh_clean = cleanup_small_clusters(lh, nb_l, min_size=min_size)
    logger.info('cleaning rh (%d verts, %d non-background)',
                rh.size, int((rh != 0).sum()))
    rh_clean = cleanup_small_clusters(rh, nb_r, min_size=min_size)

    n_changed_l = int((lh_clean != lh).sum())
    n_changed_r = int((rh_clean != rh).sum())
    logger.info('reassigned lh=%d rh=%d verts', n_changed_l, n_changed_r)

    out = np.concatenate([lh_clean, rh_clean]).astype(np.int32).reshape(1, -1)

    # Preserve original CIFTI label table + brain-model axis
    new_img = nib.Cifti2Image(out, header=img.header,
                              nifti_header=img.nifti_header)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(new_img, str(out_path))
    logger.info('wrote %s', out_path)


def derive_output_path(in_path: Path, min_size: int) -> Path:
    """sub-s10_MSHBM.dlabel.nii → sub-s10_MSHBM_minsize-30.dlabel.nii"""
    name = in_path.name
    if name.endswith('.dlabel.nii'):
        stem = name[:-len('.dlabel.nii')]
        return in_path.with_name(f'{stem}_minsize-{min_size}.dlabel.nii')
    return in_path.with_name(in_path.stem + f'_minsize-{min_size}' + in_path.suffix)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('inputs', nargs='+', type=Path,
                   help='One or more dlabel.nii files to clean up')
    p.add_argument('--min-size', type=int, default=30,
                   help='Minimum cluster size in grayordinates (default: 30)')
    p.add_argument('--output', type=Path, default=None,
                   help=('Optional explicit output path. Only valid with a '
                         'single input. Default: alongside input with '
                         '_minsize-{N} suffix.'))
    p.add_argument('--verbose', action='store_true')
    args = p.parse_args(argv)

    logging.basicConfig(
        format='%(asctime)s %(levelname)s: %(message)s', datefmt='%H:%M:%S',
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    if args.output is not None and len(args.inputs) != 1:
        logger.error('--output is only valid with exactly one input')
        return 2

    for src in args.inputs:
        if not src.is_file():
            logger.error('missing input: %s', src)
            return 1
        dst = args.output if args.output else derive_output_path(src, args.min_size)
        if dst.resolve() == src.resolve():
            logger.error('refusing to overwrite input: %s', src)
            return 1
        cleanup_dlabel(src, dst, min_size=args.min_size)

    return 0


if __name__ == '__main__':
    sys.exit(main())
