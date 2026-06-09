"""Min-size cluster cleanup for MSHBM fsaverage6 dlabel.nii outputs.

Ports the algorithm from Godfrey's ReproTM ``minsize_v1.0.0.py`` (which
operates on fsLR_91k dconn-derived dscalars) to fsaverage6 surface dlabels.

Algorithm per hemisphere, per network:
  1. Find connected components of vertices sharing the network label.
  2. For each component < ``min_size``, reassign its vertices to the
     mode network label of their neighbors (excluding the component itself).

Operates on raw integer label arrays — caller is responsible for reading
the CIFTI dlabel and re-saving the result.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np


def build_neighbors_from_faces(faces: np.ndarray, n_vertices: int) -> list[set[int]]:
    """Build per-vertex neighbor sets from a triangle face list.

    Parameters
    ----------
    faces
        ``(F, 3)`` int array — each row is three vertex indices forming a triangle.
    n_vertices
        Total vertex count (so isolated verts get an empty set).
    """
    neighbors: list[set[int]] = [set() for _ in range(n_vertices)]
    for a, b, c in faces:
        neighbors[a].add(b); neighbors[a].add(c)
        neighbors[b].add(a); neighbors[b].add(c)
        neighbors[c].add(a); neighbors[c].add(b)
    return neighbors


def find_clusters(labels: np.ndarray, neighbors: list[set[int]]) -> dict[int, list[np.ndarray]]:
    """Connected-component labeling per network value.

    Returns ``{network_label: [array_of_vertex_indices, ...]}`` — one entry
    per (label, component).
    """
    n = labels.shape[0]
    visited = np.zeros(n, dtype=bool)
    clusters: dict[int, list[np.ndarray]] = {}
    for seed in range(n):
        if visited[seed]:
            continue
        label = int(labels[seed])
        stack = [seed]
        component: list[int] = []
        while stack:
            v = stack.pop()
            if visited[v]:
                continue
            if int(labels[v]) != label:
                continue
            visited[v] = True
            component.append(v)
            stack.extend(neighbors[v])
        clusters.setdefault(label, []).append(np.array(component, dtype=np.int64))
    return clusters


def cleanup_small_clusters(
    labels: np.ndarray,
    neighbors: list[set[int]],
    min_size: int,
    background_label: int = 0,
) -> np.ndarray:
    """Reassign clusters smaller than ``min_size`` to the mode of their
    out-of-cluster neighbors.

    The ``background_label`` (medial wall, value 0 in CIFTI label files)
    is left untouched — its "clusters" are never reassigned, and it is
    excluded from neighbor-mode votes.

    Iterates until no small clusters remain (small clusters can re-form
    after a single pass when a neighboring small cluster reassigns first).
    """
    labels = labels.copy().astype(np.int64)
    while True:
        clusters = find_clusters(labels, neighbors)
        changed = False
        for label, comps in clusters.items():
            if label == background_label:
                continue
            for comp in comps:
                if comp.size >= min_size:
                    continue
                # Collect labels of neighbors that lie outside this component
                in_comp = set(int(v) for v in comp)
                votes: Counter[int] = Counter()
                for v in comp:
                    for n in neighbors[v]:
                        if n in in_comp:
                            continue
                        nlabel = int(labels[n])
                        if nlabel == background_label:
                            continue
                        votes[nlabel] += 1
                if not votes:
                    # Isolated component touching only background — leave it
                    continue
                new_label = votes.most_common(1)[0][0]
                labels[comp] = new_label
                changed = True
        if not changed:
            break
    return labels


def fsaverage6_pial_path(hemi: str, templateflow_root: Path | None = None) -> Path:
    """Resolve the templateflow fsaverage6 (den-41k) pial path for a hemisphere."""
    root = templateflow_root or (Path.home() / '.cache' / 'templateflow')
    return root / 'tpl-fsaverage' / f'tpl-fsaverage_hemi-{hemi}_den-41k_pial.surf.gii'
