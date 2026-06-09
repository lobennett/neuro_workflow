"""Tests for the fsaverage6 min-size cluster cleanup."""
from __future__ import annotations

import numpy as np
import pytest


def test_build_neighbors_from_faces_simple_triangle():
    """A single triangle: each of 3 verts has the other two as neighbors."""
    from neuro_workflow.analysis.mshbm.minsize import build_neighbors_from_faces

    faces = np.array([[0, 1, 2]], dtype=np.int64)
    nb = build_neighbors_from_faces(faces, n_vertices=3)
    assert nb[0] == {1, 2}
    assert nb[1] == {0, 2}
    assert nb[2] == {0, 1}


def test_find_clusters_separates_disconnected_same_label():
    """Two disconnected vertex sets sharing a label form two clusters."""
    from neuro_workflow.analysis.mshbm.minsize import find_clusters

    # 6 verts arranged as two disjoint triangles 0-1-2 and 3-4-5
    neighbors = [{1, 2}, {0, 2}, {0, 1}, {4, 5}, {3, 5}, {3, 4}]
    labels = np.array([1, 1, 1, 1, 1, 1], dtype=np.int64)
    clusters = find_clusters(labels, neighbors)
    assert 1 in clusters
    comps = clusters[1]
    assert len(comps) == 2
    sizes = sorted(c.size for c in comps)
    assert sizes == [3, 3]


def test_cleanup_small_clusters_reassigns_to_mode_of_neighbors():
    """A 1-vert cluster surrounded by label-2 neighbors gets relabeled to 2."""
    from neuro_workflow.analysis.mshbm.minsize import cleanup_small_clusters

    # Vert 0 has label 1; its 4 neighbors all have label 2.
    # Verts 1-4 are mutually connected (form a big cluster).
    neighbors = [{1, 2, 3, 4}, {0, 2, 3, 4}, {0, 1, 3, 4}, {0, 1, 2, 4}, {0, 1, 2, 3}]
    labels = np.array([1, 2, 2, 2, 2], dtype=np.int64)
    out = cleanup_small_clusters(labels, neighbors, min_size=3)
    # vert 0's cluster has size 1 < 3, neighbors are all label 2 → reassign
    assert out[0] == 2
    # The label-2 cluster (verts 1-4) stays at 2
    assert (out[1:] == 2).all()


def test_cleanup_preserves_large_clusters():
    """Clusters >= min_size are untouched."""
    from neuro_workflow.analysis.mshbm.minsize import cleanup_small_clusters

    # 5-vert connected cluster with label 7, all neighbors of each other
    n = 5
    neighbors = [set(range(n)) - {i} for i in range(n)]
    labels = np.array([7] * n, dtype=np.int64)
    out = cleanup_small_clusters(labels, neighbors, min_size=3)
    np.testing.assert_array_equal(out, labels)


def test_cleanup_ignores_background_label():
    """Background label (0) clusters are never reassigned."""
    from neuro_workflow.analysis.mshbm.minsize import cleanup_small_clusters

    # 1 background vert (label 0) surrounded by label 1.
    # Without the background carve-out, it would flip to 1 since 1 < min_size=3.
    neighbors = [{1, 2, 3, 4}, {0, 2, 3, 4}, {0, 1, 3, 4}, {0, 1, 2, 4}, {0, 1, 2, 3}]
    labels = np.array([0, 1, 1, 1, 1], dtype=np.int64)
    out = cleanup_small_clusters(labels, neighbors, min_size=3, background_label=0)
    assert out[0] == 0


def test_fsaverage6_pial_path_returns_expected_template_path(tmp_path):
    from neuro_workflow.analysis.mshbm.minsize import fsaverage6_pial_path

    p = fsaverage6_pial_path('L', templateflow_root=tmp_path)
    assert p.name == 'tpl-fsaverage_hemi-L_den-41k_pial.surf.gii'
    assert p.parent.name == 'tpl-fsaverage'
