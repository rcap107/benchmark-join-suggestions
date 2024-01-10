import logging
import os
import pickle
from pathlib import Path
from pprint import pprint

import polars as pl
from joblib import dump, load

from src.data_structures.join_discovery_methods import (
    CountVectorizerIndex,
    ExactMatchingIndex,
    LazoIndex,
    MinHashIndex,
)
from src.data_structures.metadata import (
    CandidateJoin,
    MetadataIndex,
    QueryResult,
    RawDataset,
)

logger = logging.getLogger("join_discovery_logger")

DEFAULT_INDEX_DIR = Path("data/metadata/_indices")
DEFAULT_QUERY_RESULT_DIR = Path("results/query_results")


def prepare_default_configs(data_dir, selected_indices=None):
    """Prepare default configurations for various indexing methods and provide the
    data directory that contains the metadata of the tables to be indexed.

    Args:
        data_dir (str): Path to the directory that contains the metadata.
        selected_indices (str, optional): If provided, prepare and run only the selected indices.

    Raises:
        IOError: Raise IOError if `data_dir` is incorrect.

    Returns:
        dict: Configuration dictionary
    """
    if Path(data_dir).exists():
        configs = {
            "lazo": {
                "data_dir": data_dir,
                "partition_size": 50_000,
                "host": "localhost",
                "port": 15449,
            },
            "minhash": {
                "data_dir": data_dir,
                "thresholds": [20],
                "oneshot": True,
                "num_perm": 128,
                "n_jobs": -1,
            },
            "count_vectorizer": {
                "data_dir": data_dir,
            },
        }
        if selected_indices is not None:
            return {
                index_name: config
                for index_name, config in configs.items()
                if index_name in selected_indices
            }
        else:
            return configs
    else:
        raise IOError(f"Invalid path {data_dir}")


def get_candidates(query_table, query_column, indices):
    """Given query table and column, query the required indices and produce the
    candidates. Used for debugging.

    Args:
        query_table (_type_): _description_
        query_column (_type_): _description_
        indices (_type_): _description_
    """
    pass


def save_single_table(dataset_path, dataset_source, metadata_dest):
    ds = RawDataset(dataset_path, dataset_source, metadata_dest)
    ds.save_metadata_to_json()


def write_candidates_on_file(candidates, output_file_path, separator=","):
    with open(output_file_path, "w") as fp:
        fp.write("tbl_pth1,tbl1,col1,tbl_pth2,tbl2,col2\n")

        for key, cand in candidates.items():
            rstr = cand.get_joinpath_str(sep=separator)
            fp.write(rstr + "\n")

    # open output file

    # write the candidates

    # metam format is left_table;left_on_column;right_table;right_on_column


def generate_candidates(
    index_name: str,
    index_result: list,
    metadata_index: MetadataIndex,
    mdata_source: dict,
    query_column: str,
    top_k=15,
):
    candidates = {}
    for res in index_result:
        hash_, column, similarity = res
        mdata_cand = metadata_index.query_by_hash(hash_)
        cjoin = CandidateJoin(
            indexing_method=index_name,
            source_table_metadata=mdata_source,
            candidate_table_metadata=mdata_cand,
            how="left",
            left_on=query_column,
            right_on=column,
            similarity_score=similarity,
        )
        candidates[cjoin.candidate_id] = cjoin

    if top_k > 0:
        # TODO rewrite this so it's cleaner
        ranking = [(k, v.similarity_score) for k, v in candidates.items()]
        clamped = [x[0] for x in sorted(ranking, key=lambda x: x[1], reverse=True)][
            :top_k
        ]

        candidates = {k: v for k, v in candidates.items() if k in clamped}
    return candidates


def prepare_join_discovery_methods(index_configurations: dict):
    """Given a dict of index configurations, initialize the required indices.

    Args:
        index_configurations (dict): Dictionary that contains the required configurations.

    Raises:
        NotImplementedError: Raise NotImplementedError when providing an index that is not recognized.

    """

    for index, config in index_configurations.items():
        for i_conf in config:
            metadata_dir = Path(i_conf["metadata_dir"])
            pprint(i_conf, indent=2)
            case = metadata_dir.stem
            if "thresholds" in i_conf:
                case += f"_{i_conf['thresholds']}"
            index_dir = Path(f"data/metadata/_indices/{case}")
            os.makedirs(index_dir, exist_ok=True)
            if "base_table_path" in i_conf:
                logger.info(
                    "Index creation start: %s - %s - %s"
                    % (case, index, i_conf["base_table_path"])
                )
            else:
                logger.info("Index creation start: %s - %s " % (case, index))
            if index == "lazo":
                this_index = LazoIndex(**i_conf)
            elif index == "minhash":
                this_index = MinHashIndex(**i_conf)
            elif index == "count_vectorizer":
                this_index = CountVectorizerIndex(**i_conf)
            elif index == "exact_matching":
                this_index = ExactMatchingIndex(**i_conf)
            else:
                raise NotImplementedError
            logger.info("Index creation end: %s - %s " % (case, index))

            this_index.save_index(index_dir)


def save_indices(index_dict: dict, index_dir: str | Path):
    """Save all the indices found in `index_dict` in separate pickle files, in the
    directory provided in `index_dir`.

    Args:
        index_dict (dict): Dictionary containing the indices.
        index_dir (str): Path where the dictionaries will be saved.
    """
    if Path(index_dir).exists():
        for index_name, index in index_dict.items():
            print(f"Saving index {index_name}")
            filename = f"{index_name}_index.pickle"
            fpath = Path(index_dir, filename)
            index.save_index(fpath)
    else:
        raise ValueError(f"Invalid `index_dir` {index_dir}")


def load_index(config):
    jd_method = config["join_discovery_method"]
    data_lake_version = config["data_lake"]

    index_path = Path(DEFAULT_INDEX_DIR, data_lake_version, f"{jd_method}_index.pickle")

    if jd_method == "minhash":
        with open(index_path, "rb") as fp:
            input_dict = load(fp)
        index = MinHashIndex()
        index.load_index(index_dict=input_dict)
    elif jd_method == "lazo":
        index = LazoIndex()
        index.load_index(index_path)
    else:
        raise ValueError(f"Unknown index {jd_method}.")
    return index


def query_index(
    index: MinHashIndex | LazoIndex,
    query_tab_path,
    query_column,
    mdata_index,
    rerank: bool = False,
):
    query_tab_metadata = RawDataset(
        query_tab_path.resolve(), "queries", "data/metadata/queries"
    )
    query_tab_metadata.save_metadata_to_json()

    query_result = QueryResult(
        index, query_tab_metadata, query_column, mdata_index, rerank
    )
    query_result.save_to_pickle()
    return query_result


def load_query_result(yadl_version, index_name, tab_name, query_column, top_k):
    query_result_path = "{}__{}__{}__{}.pickle".format(
        yadl_version,
        index_name,
        tab_name,
        query_column,
    )

    with open(
        Path(DEFAULT_QUERY_RESULT_DIR, yadl_version, query_result_path), "rb"
    ) as fp:
        query_result = pickle.load(fp)

    query_result.select_top_k(top_k)
    return query_result
