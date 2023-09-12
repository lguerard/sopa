import argparse
from math import ceil
from pathlib import Path

import numpy as np
import pandas as pd
import zarr


def subsample_indices(n_samples, factor: int = 4):
    n_sub = n_samples // factor
    return np.random.choice(n_samples, n_sub, replace=False)


MAX_LEVELS = 15
GRID_SIZE = 250
QUALITY_SCORE = 40


def write_transcripts(
    path: Path, df: pd.DataFrame, x: str = "x", y: str = "y", gene: str = "gene"
):
    num_transcripts = len(df)
    df[gene] = df[gene].astype("category")

    location = df[[x, y]]
    location = np.concatenate([location, np.zeros((num_transcripts, 1))], axis=1)

    xmax, ymax = location[:, :2].max(axis=0)

    assert location[:, 0].min() >= 0
    assert location[:, 1].min() >= 0

    gene_names = list(df[gene].cat.categories)
    num_genes = len(gene_names)

    codeword_gene_mapping = list(range(num_genes))

    valid = np.ones((num_transcripts, 1))
    uuid = np.stack(
        [np.arange(num_transcripts), np.full(num_transcripts, 65535)], axis=1
    )
    transcript_id = np.stack(
        [np.arange(num_transcripts), np.full(num_transcripts, 65535)], axis=1
    )
    gene_identity = df[gene].cat.codes.values[:, None]
    codeword_identity = np.stack(
        [gene_identity[:, 0], np.full(num_transcripts, 65535)], axis=1
    )
    status = np.zeros((num_transcripts, 1))
    quality_score = np.full((num_transcripts, 1), QUALITY_SCORE)

    ATTRS = {
        "codeword_count": num_genes,
        "codeword_gene_mapping": codeword_gene_mapping,
        "codeword_gene_names": gene_names,
        "gene_names": gene_names,
        "gene_index_map": {
            name: index for name, index in zip(gene_names, codeword_gene_mapping)
        },
        "number_genes": num_genes,
        "spatial_units": "micron",
        "coordinate_space": "refined-final_global_micron",
        "major_version": 4,
        "minor_version": 1,
        "name": "RnaDataset",
        "number_rnas": num_transcripts,
        "dataset_uuid": "unique-id-test",
        "data_format": 0,
    }

    GRIDS_ATTRS = {
        "grid_key_names": ["grid_x_loc", "grid_y_loc"],
        "grid_zip": False,
        "grid_size": [GRID_SIZE],
        "grid_array_shapes": [],
        "grid_number_objects": [],
        "grid_keys": [],
    }

    if path.exists():
        path.unlink()

    with zarr.ZipStore(path, mode="w") as store:
        g = zarr.group(store=store)
        g.attrs.put(ATTRS)

        grids = g.create_group("grids")

        for level in range(MAX_LEVELS):
            level_group = grids.create_group(level)

            tile_size = GRID_SIZE * 2**level

            print(f"Level {level}: {len(location)} transcripts")

            indices = np.floor(location[:, :2] / tile_size).clip(0).astype(int)
            tiles_str_indices = np.array([f"{tx},{ty}" for (tx, ty) in indices])

            GRIDS_ATTRS["grid_array_shapes"].append([])
            GRIDS_ATTRS["grid_number_objects"].append([])
            GRIDS_ATTRS["grid_keys"].append([])

            n_tiles_x, n_tiles_y = ceil(xmax / tile_size), ceil(ymax / tile_size)

            for tx in range(n_tiles_x):
                for ty in range(n_tiles_y):
                    str_index = f"{tx},{ty}"
                    loc = np.where(tiles_str_indices == str_index)[0]

                    n_points_tile = len(loc)
                    chunks = (n_points_tile, 1)

                    if n_points_tile == 0:
                        continue

                    GRIDS_ATTRS["grid_array_shapes"][-1].append({})
                    GRIDS_ATTRS["grid_keys"][-1].append(str_index)
                    GRIDS_ATTRS["grid_number_objects"][-1].append(n_points_tile)

                    tile_group = level_group.create_group(str_index)
                    tile_group.array(
                        "valid",
                        valid[loc],
                        dtype="uint8",
                        chunks=chunks,
                    )
                    tile_group.array(
                        "status",
                        status[loc],
                        dtype="uint8",
                        chunks=chunks,
                    )
                    tile_group.array(
                        "location",
                        location[loc],
                        dtype="float32",
                        chunks=chunks,
                    )
                    tile_group.array(
                        "gene_identity",
                        gene_identity[loc],
                        dtype="uint16",
                        chunks=chunks,
                    )
                    tile_group.array(
                        "quality_score",
                        quality_score[loc],
                        dtype="float32",
                        chunks=chunks,
                    )
                    tile_group.array(
                        "codeword_identity",
                        codeword_identity[loc],
                        dtype="uint16",
                        chunks=chunks,
                    )
                    tile_group.array(
                        "uuid",
                        uuid[loc],
                        dtype="uint32",
                        chunks=chunks,
                    )
                    tile_group.array(
                        "id",
                        transcript_id[loc],
                        dtype="uint32",
                        chunks=chunks,
                    )

            if n_tiles_x * n_tiles_y == 1:
                GRIDS_ATTRS["number_levels"] = level + 1
                break

            sub_indices = subsample_indices(len(location))

            location = location[sub_indices]
            valid = valid[sub_indices]
            status = status[sub_indices]
            gene_identity = gene_identity[sub_indices]
            quality_score = quality_score[sub_indices]
            codeword_identity = codeword_identity[sub_indices]
            uuid = uuid[sub_indices]
            transcript_id = transcript_id[sub_indices]

        grids.attrs.put(GRIDS_ATTRS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-p",
        "--path",
        type=str,
        required=True,
        help="Path to the zarr.zip file to be created",
    )
    parser.add_argument(
        "-d",
        "--data",
        type=str,
        required=True,
        help="Path to the pandas transcript file",
    )

    args = parser.parse_args()
    write_transcripts(args.path, pd.read_csv(args.data))