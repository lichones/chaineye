"""
Memory-lean feature store for ChainEye inference.

Loads the (203k x 165) float32 feature matrix as a memory-mapped numpy array
instead of a full pandas DataFrame. This keeps resident RAM near-zero for the
feature table (only touched rows are paged in) and, critically, avoids the large
transient allocation that pandas/pyarrow incur when converting a single-row-group
parquet into a DataFrame.

On first use it builds two on-disk caches next to the parquet:
    feature_table.f32.npy   - (n_rows, 165) float32 matrix (memmap)
    feature_table.txid.npy  - (n_rows,) int64 txIds, aligned row-for-row

Building writes column-by-column straight into the on-disk memmap, so peak RAM
during the (one-time) build stays low. Subsequent process starts just mmap the
existing cache with essentially no resident cost.

Values are identical to the parquet (already float32), so model outputs are
unchanged.
"""
import os
import numpy as np

N_FEATURES = 165
FEATURE_COLS = [f"feat_{i}" for i in range(N_FEATURES)]


def _cache_paths(parquet_path: str):
    base = os.path.splitext(parquet_path)[0]
    return base + ".f32.npy", base + ".txid.npy"


def _cache_is_valid(mat_path: str, tx_path: str, parquet_path: str) -> bool:
    if not (os.path.exists(mat_path) and os.path.exists(tx_path)):
        return False
    # rebuild if the source parquet is newer than the cache
    src_m = os.path.getmtime(parquet_path)
    return os.path.getmtime(mat_path) >= src_m and os.path.getmtime(tx_path) >= src_m


def _build_cache(parquet_path: str, mat_path: str, tx_path: str) -> None:
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(parquet_path)
    n = pf.metadata.num_rows

    tmp_mat = mat_path + ".tmp"
    tmp_tx = tx_path + ".tmp"

    # write matrix straight into an on-disk memmap, one column at a time so we
    # never hold more than a single decompressed column in RAM at once
    mm = np.lib.format.open_memmap(
        tmp_mat, mode="w+", dtype=np.float32, shape=(n, N_FEATURES)
    )
    try:
        for j, name in enumerate(FEATURE_COLS):
            tbl = pq.read_table(parquet_path, columns=[name])
            mm[:, j] = tbl.column(0).to_numpy(zero_copy_only=False)
            del tbl
        mm.flush()
    finally:
        del mm

    tbl = pq.read_table(parquet_path, columns=["txId"])
    txids = np.asarray(tbl.column(0).to_numpy(zero_copy_only=False), dtype=np.int64)
    del tbl
    with open(tmp_tx, "wb") as fh:
        np.save(fh, txids)
    del txids

    os.replace(tmp_mat, mat_path)
    os.replace(tmp_tx, tx_path)


def load_feature_matrix(parquet_path: str):
    """Return (matrix, row_index).

    matrix    : read-only float32 memmap, shape (n_rows, 165)
    row_index : dict {txId(int) -> row position(int)}
    """
    mat_path, tx_path = _cache_paths(parquet_path)
    if not _cache_is_valid(mat_path, tx_path, parquet_path):
        _build_cache(parquet_path, mat_path, tx_path)

    matrix = np.load(mat_path, mmap_mode="r")
    txids = np.load(tx_path)  # int64, ~1.6MB
    # keep the FIRST occurrence for any (non-existent here) duplicate txId
    row_index = {}
    for i in range(txids.shape[0]):
        row_index.setdefault(int(txids[i]), i)
    del txids
    return matrix, row_index
