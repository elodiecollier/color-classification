"""ClusteringStrategy: HDBSCAN alternative (§7).

Implements ports/clustering.py. Density-based — no k to choose, which may
handle gradient swatches more gracefully than the k-sweep. Noise points
(label -1) fold into coverage accounting rather than becoming a cluster.

Exists to be A/B'd against kmeans_sweep.py on real swatches; whichever
wins becomes the default wired up in cli/run_batch.py.
"""
