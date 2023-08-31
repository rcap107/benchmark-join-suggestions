from abc import abstractmethod
from itertools import product

import numpy as np
import pandas as pd

try:
    import polars as pl
    import polars.selectors as cs

    # TODO: Enable polars accross the library
    POLARS_SETUP = True
except ImportError:
    POLARS_SETUP = False

from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.utils.validation import check_is_fitted
import sklearn.feature_selection as fs
import sklearn.metrics as metrics
from difflib import SequenceMatcher


NUM_OPS = ["sum", "mean", "std", "min", "max"]
CATEG_OPS = ["mode"]
ALL_OPS = NUM_OPS + CATEG_OPS

PANDAS_OPS_MAPPING = {"mode": pd.Series.mode}


def split_num_categ_ops(agg_ops):
    """Separate aggregagor operators input
    by their type.

    Parameters
    ----------
    agg_ops : list of str,
        The input operators names.

    Returns
    -------
    num_ops, categ_ops : Tuple of List of str
        List of operator names
    """
    num_ops, categ_ops = [], []
    for op_name in agg_ops:
        if op_name in NUM_OPS:
            num_ops.append(op_name)
        elif op_name in CATEG_OPS:
            categ_ops.append(op_name)
        else:
            raise ValueError(f"'agg_ops' options are {ALL_OPS}, got: '{op_name}'.")
    return num_ops, categ_ops


def dispatch_assembling_engine(tables):
    """Returns the AssemblingEngine implementation for given tables
    module.

    Parameters
    ----------
    tables : List of Tuple of (table, cols_to_join, cols_to_agg)
        We only use table to detect the module used.

    Returns
    -------
    assembling_engine : AssemblingEngine
        The suited AssemblingEngine implementation.
    """

    use_pandas = all([isinstance(table, pd.DataFrame) for table, _, _ in tables])
    use_polars = False
    if POLARS_SETUP:
        # we don't mix DataFrame and LazyFrame
        use_polars = all(
            [isinstance(table, pl.DataFrame) for table, _, _ in tables]
        ) or all([isinstance(table, pl.LazyFrame) for table, _, _ in tables])
    if use_pandas:
        return PandasAssemblingEngine()
    elif use_polars:
        return PolarsAssemblingEngine()
    else:
        raise NotImplementedError(
            "Only Pandas or Polars dataframes are currently supported."
        )


class AssemblingEngine:
    """Helper class to perform the join and aggregate operations.

    This is an abstract base class that is specialized depending
    on the module of the dataframe used (Pandas or Polars).
    """

    @abstractmethod
    def agg(self, table, cols_to_join, cols_to_agg, agg_ops, suffix):
        pass

    @abstractmethod
    def join(self, left, right, left_on, right_on):
        pass


class PandasAssemblingEngine(AssemblingEngine):
    def agg(self, table, cols_to_join, cols_to_agg, agg_ops, suffix):
        def get_agg_ops(cols, agg_ops):
            stats = {}
            for col, op_name in product(cols, agg_ops):
                op = PANDAS_OPS_MAPPING.get(op_name, op_name)
                stats[f"{col}_{op_name}"] = pd.NamedAgg(col, op)
            return stats

        def split_num_categ_cols(table):
            num_cols = table.select_dtypes("number").columns
            categ_cols = table.select_dtypes(["object", "string", "category"]).columns
            return num_cols, categ_cols

        num_cols, categ_cols = split_num_categ_cols(table[cols_to_agg])
        num_ops, categ_ops = split_num_categ_ops(agg_ops)

        num_stats = get_agg_ops(num_cols, num_ops)
        categ_stats = get_agg_ops(categ_cols, categ_ops)

        table = table.groupby(cols_to_join).agg(**num_stats, **categ_stats)
        table.columns = [
            f"{col}{suffix}" if col not in cols_to_join else col
            for col in table.columns
        ]

        return table

    def join(self, left, right, left_on, right_on):
        return left.merge(
            right,
            how="left",
            left_on=left_on,
            right_on=right_on,
        )


class PolarsAssemblingEngine(AssemblingEngine):
    def agg(self, table, cols_to_join, cols_to_agg, agg_ops, suffix):
        def split_num_categ_cols(table):
            num_cols = table.select(pl.col(pl.NUMERIC_DTYPES)).columns

            categ_cols = table.select(pl.col(pl.Utf8)).columns

            return num_cols, categ_cols

        def get_agg_ops(cols, agg_ops):
            stats, mode_cols = [], []
            for col, op_name in product(cols, agg_ops):
                out_name = f"{col}_{op_name}"
                op_dict = {
                    "mean": pl.col(col).mean().alias(out_name),
                    "std": pl.col(col).std().alias(out_name),
                    "sum": pl.col(col).sum().alias(out_name),
                    "min": pl.col(col).min().alias(out_name),
                    "max": pl.col(col).max().alias(out_name),
                    "mode": pl.col(col).mode().alias(out_name),
                }
                op = op_dict.get(op_name, None)
                if op is None:
                    raise ValueError(
                        f"Polars operation '{op}' is not supported. "
                        f"Available: {list(op_dict)}"
                    )
                stats.append(op)

                # mode() output needs a flattening post-processing
                if op_name == "mode":
                    mode_cols.append(out_name)

            return stats, mode_cols

        num_cols, categ_cols = split_num_categ_cols(table.select(cols_to_agg))

        num_ops, categ_ops = split_num_categ_ops(agg_ops)

        num_ops, num_mode_cols = get_agg_ops(num_cols, num_ops)
        categ_ops, categ_mode_cols = get_agg_ops(categ_cols, categ_ops)

        all_ops = [*num_ops, *categ_ops]
        table = table.groupby(cols_to_join).agg(all_ops)

        # flattening post-processing of mode() cols
        flatten_ops = []
        for col in [*num_mode_cols, *categ_mode_cols]:
            flatten_ops.append(pl.col(col).list[0].alias(col))
        table = table.with_columns(flatten_ops)

        cols_renaming = {
            col: f"{col}{suffix}" for col in table.columns if col not in cols_to_join
        }
        table = table.rename(cols_renaming)

        return table

    def join(self, left, right, left_on, right_on):
        return left.join(
            right,
            how="left",
            left_on=left_on,
            right_on=right_on,
        )


class JoinAggregator(BaseEstimator, TransformerMixin):
    """Perform aggregation on auxiliary dataframes before joining
    on the base dataframe.

    Apply numerical (mean, std, sum, min, max) and categorical (mode)
    aggregation operations on the columns to aggregate, selected by dtypes.

    The grouping columns used during the aggregation are the columns used
    as keys for joining.

    Uses :obj:`~pandas.DataFrame` inputs only.

    Parameters
    ----------
    tables : list of tuples
        List of (dataframe, columns_to_join, columns_to_agg) tuple
        specifying the auxiliary dataframes and their columns for joining
        and aggregation operations.

        dataframe : :obj:`~pandas.DataFrame` or str
            The auxiliary data to aggregate and join.
            'X' can be provided as a string to perform self-aggregation on
            the input data.

        columns_to_join : str or array-like
            Select the columns from the dataframe to use as keys during
            the join operation.

        columns_to_agg : str or array-like
            Select the columns from the dataframe to use as values during
            the aggregation operations.

    main_key : str or array-like
        Select the columns from the base table to use as keys during
        the join operation.
        If main_key refer to a single column, it will be used to join all tables.
        Otherwise, main_key must specify the key for each table to join.

    agg_ops : str or list of str, default=None
        Aggregation operations to perform on the auxiliary table.
        Options: {'mean', 'std', 'min', 'max', 'mode'}. If set to None,
        ['mean', 'mode'] will be used.

    suffixes : list of str, default=None
        The suffixes that will be add to each table columns in case of
        duplicate column names, similar to `("_x", "_y")` in :obj:`~pandas.merge`.
        If set to None, we will use the table index, by looking at their
        order in 'tables', e.g. for a duplicate columns: price, price_1, price_2.

    See Also
    --------
    :class:`FeatureAugmenter` :
        Augment a main table by automatically joining multiple
        auxiliary tables on it.
    """

    def __init__(self, tables, main_key, agg_ops=None, suffixes=None):
        self.tables = tables
        self.main_key = main_key
        self.agg_ops = agg_ops
        self.suffixes = suffixes

    def fit(self, X, y=None):
        """Fit the instance to the auxiliary tables by aggregating them
        and storing the outputs.

        Parameters
        ----------
        X : {pandas.Dataframe}
            Input data, based table on which to left join the
            auxiliary tables..

        y : array-like of shape (n_samples), default=None
            Used to compute the correlation between the generated covariates
            and the target for screening purposes.

        Returns
        -------
        :obj:`JoinAggregator`
            Fitted :class:`JoinAggregator` instance (self).
        """
        self.check_cols(X)

        # TODO: filter 'tables' using X, before aggregation

        if self.agg_ops is None:
            agg_ops = ["mean", "mode"]
        else:
            agg_ops = np.atleast_1d(self.agg_ops).tolist()
        self.agg_ops_ = agg_ops

        self.assembly_engine = dispatch_assembling_engine(self.tables)

        self.agg_tables_ = []
        for (table, cols_to_join, cols_to_agg), suffix, main_key in zip(
            self.tables, self.suffixes_, self.main_keys_
        ):
            agg_table = self.assembly_engine.agg(
                table,
                cols_to_join,
                cols_to_agg,
                agg_ops,
                suffix,
            )
            agg_table = self._screen(agg_table, y, X, main_key, cols_to_join)

            self.agg_tables_.append((agg_table, cols_to_join))

        return self

    def transform(self, X):
        """Transform `X` by left joining the pre-aggregated
        auxiliary tables to it.

        Parameters
        ----------
        X : pandas.DataFrame
            The input data to transform.
        """

        check_is_fitted(self, "agg_tables_")

        for main_key, (aux, aux_key) in zip(self.main_keys_, self.agg_tables_):
            X = self.assembly_engine.join(
                left=X,
                right=aux,
                left_on=main_key,
                right_on=aux_key,
            )

        return X

    def _screen(
        self, agg_table, y, X: pl.DataFrame, left_on, right_on, threshold=50, top_k=None
    ):
        """Only keep aggregated features which correlation with
        y is above some threshold.
        """
        return agg_table

        def metric_selection(
            agg_table: pl.DataFrame, y: pl.Series, target_columns: pl.Series
        ):
            header = ["col_name", "type", "metric"]
            metrics_list = []
            num_cols = agg_table.select(cs.numeric() & cs.by_name(target_columns))
            cat_cols = agg_table.select(cs.string() & cs.by_name(target_columns))

            for col in num_cols:
                metrics_list.append(
                    dict(zip(header, (col.name, "numeric", metric_numerical(col, y))))
                )

            for col in cat_cols:
                metrics_list.append(
                    dict(zip(header, (col.name, "discrete", metric_discrete(col, y))))
                )
            df_measures = pl.from_dicts(metrics_list)
            return df_measures

        def metric_numerical(col, y):
            is_null = col.is_null().to_numpy()
            if sum(is_null) == len(col):
                return 0
            filled_null = col.fill_null(strategy="mean").to_numpy()

            _, p_nulls = fs.f_regression(is_null.reshape(-1, 1), y)
            _, p_filled = fs.f_regression(filled_null.reshape(-1, 1), y)

            return np.mean([-np.log(p_nulls), -np.log(p_filled)])

        def metric_discrete(col, y):
            is_null = col.is_null().to_numpy()
            if sum(is_null) == len(col):
                return 0
            filled_null = (
                col.fill_null("null").cast(pl.Categorical).cast(pl.Int16).to_numpy()
            )

            _, p_nulls = fs.f_classif(is_null.reshape(-1, 1), y)
            _, p_filled = fs.f_classif(filled_null.reshape(-1, 1), y)

            if p_filled == 0:
                p_filled = [1]
            if p_nulls == 0:
                p_nulls = [1]

            return np.mean([-np.log(p_nulls), -np.log(p_filled)])

        if y is None:
            return agg_table

        join_partial = X.select(pl.col(left_on)).join(
            agg_table,
            left_on=left_on,
            right_on=right_on,
            how="left",
        )

        cols_to_measure = [
            col for col in join_partial.columns if col not in left_on + right_on
        ]

        if top_k is None:
            top_k = len(cols_to_measure)

        df_measures = metric_selection(join_partial, y, cols_to_measure)

        selected_columns = (
            df_measures.filter(pl.col("metric") >= threshold)
            .top_k(k=top_k, by="metric")
            .select(pl.col("col_name"))
        )

        cols_to_drop = [
            col for col in cols_to_measure if col not in selected_columns["col_name"]
        ]

        return agg_table.drop(cols_to_drop)

    def check_cols(self, X):
        """Check that all columns to join and columns to aggregate
        belong to their respective dataframes.
        """
        # Check main_keys
        main_keys = np.atleast_1d(self.main_key).tolist()
        missing_cols = set(main_keys) - set(X.columns)
        if len(missing_cols) > 0:
            raise ValueError(
                f"Got main_key={self.main_key!r}, but column not in {list(X.columns)}."
            )

        n_main_keys, n_tables = len(main_keys), len(self.tables)
        if (n_main_keys != 1) and (n_main_keys != n_tables):
            raise ValueError(
                "The number of main keys must be either 1 or "
                "match the number of tables."
            )

        # Ensure n_main_keys == n_tables
        if n_main_keys == 1:
            main_keys = [
                main_keys,
            ] * n_tables

        self.main_keys_ = main_keys

        # Check agg and join columns
        for idx, (table, cols_to_join, cols_to_agg) in enumerate(self.tables):
            cols_to_join = np.atleast_1d(cols_to_join).tolist()
            cols_to_agg = np.atleast_1d(cols_to_agg).tolist()

            if isinstance(table, str):
                if table != "X":
                    raise ValueError(f"if string, table can only be 'X', got: {table}")
                table = X.copy()
                self.tables[idx] = (table, cols_to_join, cols_to_agg)

            table_cols = set(table.columns)
            input_cols = set([*cols_to_join, *cols_to_agg])

            missing_cols = input_cols - table_cols
            if len(missing_cols) > 0:
                raise ValueError(f"{missing_cols} are missing in table {idx+1}")

        # Check suffixes
        if self.suffixes is None:
            if n_tables == 1:
                suffixes = [""]
            else:
                suffixes = [f"_{idx+1}" for idx in range(len(self.tables))]
        elif hasattr(self.suffixes, "__len__"):
            suffixes = np.atleast_1d(self.suffixes).tolist()
            if len(suffixes) != n_tables:
                raise ValueError(
                    "Suffixes must be None or match the "
                    f"number of tables, got: '{self.suffixes}'"
                )
        else:
            raise ValueError(
                "Suffixes must be a list of string matching "
                f"the number of tables, got: '{self.suffixes}'"
            )

        self.suffixes_ = suffixes

        return