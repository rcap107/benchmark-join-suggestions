from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd
import polars as pl
import seaborn as sns
from matplotlib.patches import Polygon

plt.style.use("seaborn-v0_8-talk")

GROUPING_KEYS = ["jd_method", "estimator", "chosen_model", "target_dl", "base_table"]

LABEL_MAPPING = {
    "base_table": {
        "company-employees-yadl-depleted": "(D) Employees",
        "movies-yadl-depleted": "(D) Movies",
        "movies-vote-yadl-depleted": "(D) Movies Vote",
        "housing-prices-yadl-depleted": "(D) Housing Prices",
        "us-accidents-yadl-depleted": "(D) US Accidents",
        "us-elections-yadl-depleted": "(D) US Elections",
    },
    "jd_method": {"exact_matching": "Exact", "minhash": "MinHash"},
    "chosen_model": {"catboost": "CatBoost", "linear": "Linear"},
    "estimator": {
        "full_join": "Full",
        "best_single_join": "Best Single",
        "stepwise_greedy_join": "Stepwise Greedy",
        "highest_containment": "Highest Jaccard",
        "nojoin": "No",
    },
    "variables": {
        "estimator": "Estimator",
        "jd_method": "Retrieval method",
        "chosen_model": "ML model",
    },
}


# Function to add jitter to data
def add_jitter(data, factor=0.1):
    return data + np.random.normal(0, factor, len(data))


def add_subplot(fig, position):
    new_ax = fig.add_subplot(*position, frameon=False)

    new_ax.spines["top"].set_color("none")
    new_ax.spines["bottom"].set_color("none")
    new_ax.spines["left"].set_color("none")
    new_ax.spines["right"].set_color("none")
    new_ax.tick_params(
        labelcolor="none", top=False, bottom=False, left=False, right=False
    )
    return new_ax


def prepare_scatterplot_labels(
    df, scatterplot_dimension, plotting_variable, colormap_name="viridis"
):
    # Prepare the labels for the scatter plot and the corresponding colors. Labels are sorted by
    scatterplot_labels = (
        df.group_by(pl.col(scatterplot_dimension))
        .agg(pl.mean(plotting_variable))
        .sort(plotting_variable)
        .select(pl.col(scatterplot_dimension).unique())
        .to_numpy()
        .squeeze()
    )
    colors = plt.colormaps[colormap_name](np.linspace(0, 1, len(scatterplot_labels)))
    scatterplot_mapping = dict(
        zip(
            scatterplot_labels,
            colors,
        )
    )
    return scatterplot_mapping


def _custom_formatter(x, pos):
    return rf"{x}x"

    if x > 1:
        return rf"{x}x"
    else:
        return rf"$\frac{{}}{{}}"


def format_xaxis(ax, case, xmax=1):
    if case == "percentage":
        ax.xaxis.set_major_locator(ticker.AutoLocator())
        ax.xaxis.set_major_formatter(ticker.PercentFormatter(xmax=xmax))
    elif case == "log":
        print("log")
        ax.set_xscale(mpl.scale.LogScale)
        ax.xaxis.set_major_locator(
            ticker.LogLocator(base=10, numticks=15, subs=[-1.5, -0.5, 0.1, 0.2])
        )
        minor_locator = ticker.LogLocator(subs=np.arange(2, 10))
        ax.xaxis.set_minor_locator(minor_locator)
        ax.xaxis.set_minor_formatter(ticker.ScalarFormatter())
        # formatter = ticker.LogFormatter(minor_thresholds=(0,0))
        # formatter.set_locs()
        # ax.xaxis.set_major_formatter(formatter)
    elif case == "linear":
        ax.xaxis.set_major_locator(ticker.AutoLocator())
        ax.xaxis.set_major_formatter(ticker.ScalarFormatter())
    elif case == "symlog":
        print("symlog")
        ax.set_xscale("symlog", base=2)
        ax.xaxis.set_major_locator(ticker.SymmetricalLogLocator(base=2, linthresh=0.5))
        ax.xaxis.set_major_formatter(ticker.FuncFormatter(_custom_formatter))
        minor_locator = ticker.SymmetricalLogLocator(
            base=2, linthresh=0.5, subs=np.arange(0.5, 3)
        )
        ax.xaxis.set_minor_locator(minor_locator)
        ax.xaxis.set_minor_formatter(ticker.FuncFormatter(_custom_formatter))

    return ax


def prepare_clean_labels(labels):
    map_dataset = {
        "company-employees-prepared": "CE",
        "movies-prepared": "CE",
        "presidential-results-prepared": "CE",
    }

    map_agg = {"base_table": "BT", "dedup": "DD", "dfs": "DFS", "none": "NO"}

    map_variant = {"binary": "B", "wordnet": "W"}
    clean_labels = []
    for label in labels:
        dataset, agg, variant = label.split("|")
        # s = f"{map_dataset[dataset]}-{map_agg[agg]}-{map_variant[variant]}"
        s = f"{map_agg[agg]}-{map_variant[variant]}"
        # print(label, s)
        clean_labels.append(s)
    return clean_labels


def prepare_input_data(df: pl.DataFrame, variable_of_interest):
    data = (
        df.with_columns(
            (
                pl.col("source_table")
                + "|"
                + pl.col("aggregation")
                + "|"
                + pl.col("target_dl")
            ).alias("key")
        )
        .select(pl.col("key"), pl.col(variable_of_interest).alias("var"))
        .to_pandas()
    )

    # Dropping one group of base table runs, it could be either wordnet or binary
    data = data.drop(data.loc[data["key"].str.endswith("base_table|wordnet")].index)
    # Converting to categories
    data["key"] = data["key"].astype("category")
    data["index"] = data["key"].cat.codes
    labels = data["key"].unique().categories.to_list()

    formatted_data = []
    for g, group in data.groupby("key"):
        formatted_data.append(group["var"].values)
    return formatted_data, labels


def get_case(label, step):
    """Choose the correct parameters for box filling and hatch depending on the case.

    Args:
        label (str): Label for the given case, has format "dataset|aggregation|yadl variant"
        step (str): Either "color" or "hatch"

    Returns:
        int: An integer value that is used to find the correct index for the task.
    """
    dataset, aggregation, variant = label.split("|")
    if step == "color":
        mapping = {
            "base_table": 0,
            "dedup": 1,
            "dfs": 2,
            "none": 3,
        }
        return mapping[aggregation]
    elif step == "hatch":
        mapping = {"binary": 0, "wordnet": 1, "base_table": 2}
        if aggregation == "base_table":
            return mapping[aggregation]
        else:
            return mapping[variant]
    else:
        raise ValueError(f"Wrong step {step}")


def prepare_boxplot(df, variable_of_interest, ylabel, yscale="lin"):
    formatted_data, labels = prepare_input_data(
        df, variable_of_interest=variable_of_interest
    )
    clean_labels = prepare_clean_labels(labels)

    labels_legend = [
        "Base table",
        "Dedup - Binary",
        "Dedup - Wordnet",
        "DFS - Binary",
        "DFS - Wordnet",
        "None - Binary",
        "None - Wordnet",
    ]

    fig, ax1 = plt.subplots(figsize=(10, 6))
    fig.subplots_adjust(left=0.075, right=0.95, top=0.9, bottom=0.25)

    bp = plt.boxplot(
        formatted_data, notch=False, sym="+", vert=True, whis=1.5, widths=1
    )
    plt.setp(bp["boxes"], color="black")
    plt.setp(bp["whiskers"], color="black")
    plt.setp(bp["fliers"], color="red", marker="+")

    colors = mpl.colormaps["tab10"].resampled(4).colors
    hatches = ["/", "\\", "."]
    num_boxes = len(formatted_data)

    legend_arguments = []

    medians = np.empty(num_boxes)
    for i in range(num_boxes):
        label = labels[i]
        box = bp["boxes"][i]
        box_x = []
        box_y = []
        for j in range(5):
            box_x.append(box.get_xdata()[j])
            box_y.append(box.get_ydata()[j])
        box_coords = np.column_stack([box_x, box_y])
        patch = Polygon(box_coords, facecolor=colors[get_case(label, "color")])
        legend_arguments.append(patch)
        patch.set_hatch(hatches[get_case(label, "hatch")])
        ax1.add_patch(patch)
        # Now draw the median lines back over what we just filled in
        med = bp["medians"][i]
        median_x = []
        median_y = []

    ax1.set_xticklabels(clean_labels, rotation=45)
    ax1.set_ylabel(ylabel)
    if yscale == "log":
        ax1.set_yscale("log")

    # Add a new x axis
    # from https://stackoverflow.com/questions/37934242/hierarchical-axis-labeling-in-matplotlib-python
    ax2 = ax1.twiny()
    ax2.spines["bottom"].set_position(("axes", -0.15))
    ax2.tick_params("both", length=0, width=0, which="minor")
    ax2.tick_params("both", direction="in", which="major")
    ax2.xaxis.set_ticks_position("bottom")
    ax2.xaxis.set_label_position("bottom")

    # Set new ticks on the new axis
    ax2.set_xticks([0, 1 / 3, 2 / 3, 1])
    ax2.xaxis.set_major_formatter(ticker.NullFormatter())
    ax2.xaxis.set_minor_locator(ticker.FixedLocator([4 / 21, 11 / 21, 18 / 21]))
    ax2.xaxis.set_minor_formatter(
        ticker.FixedFormatter(
            ["Company Employees", "Movies", "US Presidential Elections"]
        )
    )

    # legend
    plt.legend(legend_arguments[:7], labels_legend, loc="upper left")


def base_barplot(
    df: pd.DataFrame,
    x_variable="estimator",
    y_variable="r2score",
    hue_variable="chosen_model",
    col_variable="base_table",
    horizontal=True,
    sharex=False,
    col_wrap=3,
    col_order=None,
):
    if horizontal:
        x = y_variable
        y = x_variable
    else:
        x = x_variable
        y = y_variable
    ax = sns.catplot(
        data=df,
        x=x,
        y=y,
        hue=hue_variable,
        kind="box",
        col=col_variable,
        sharex=sharex,
        col_wrap=col_wrap,
        col_order=col_order,
    )

    return ax


def base_relplot(
    df: pd.DataFrame,
    x_variable="time_run",
    y_variable="r2score",
    hue_variable="chosen_model",
    style_variable="estimator",
    col_variable="base_table",
    sharex=False,
    col_wrap=3,
    col_order=None,
):
    x = x_variable
    y = y_variable

    ax = sns.relplot(
        data=df,
        x=x,
        y=y,
        hue=hue_variable,
        col=col_variable,
        style=style_variable,
        kind="scatter",
        facet_kws={"sharex": sharex, "sharey": True, "subplot_kws": {"xscale": "log"}},
        col_wrap=col_wrap,
        col_order=col_order,
    )
    return ax


def violin_plot(data, values_dict, label_mapping, target_variable, jitter_factor=0.05):
    # Use the Set3 colormap for 4 distinct colors
    colors = plt.cm.viridis(np.linspace(0, 1, 4))
    color_mapping = dict(
        zip(
            [
                "highest_containment",
                "best_single_join",
                "full_join",
                "stepwise_greedy_join",
            ],
            colors,
        )
    )
    # colors = plt.cm.viridis(np.arange(4))

    fig, axes = plt.subplots(
        nrows=2,
        ncols=1,
        sharex=True,
        # gridspec_kw={"width_ratios": [2.5, 1, 2.5, 1]},
        figsize=(6, 3),
        layout="tight",
    )
    ax_big = fig.add_subplot(111, frameon=False)
    ax_big.spines["top"].set_color("none")
    ax_big.spines["bottom"].set_color("none")
    ax_big.spines["left"].set_color("none")
    ax_big.spines["right"].set_color("none")
    ax_big.tick_params(
        labelcolor="none", top=False, bottom=False, left=False, right=False
    )

    for idx, d in enumerate(data):
        ax_violin = axes[idx]
        print(values_dict[target_variable][idx])
        # ax_violin.axhline(0, alpha=0.4, zorder=0, color="gray")

        parts = ax_violin.violinplot(d, showmedians=False, showmeans=False, vert=False)
        quartile1, medians, quartile3 = np.percentile(d, [25, 50, 75])
        ax_violin.scatter(
            medians, [1], marker="o", color="white", s=30, zorder=3, edgecolors="black"
        )
        ax_violin.annotate(
            f"{medians:.2f}",
            xy=(medians, -0.1),
            xycoords=(
                "data",
                "axes fraction",
            ),
            size="x-small",
            color="blue",
        )
        ax_violin.axvline(medians, alpha=0.7, zorder=2, color="blue")

        color_variable = values_dict["est_cat"][idx]

        for label in label_mapping["label"]:
            masked = d[values_dict["estimator"][idx] == label]
            ax_violin.scatter(
                masked,
                add_jitter(np.ones_like(masked), jitter_factor),
                color=color_mapping[label],
                marker="o",
                s=3,
                alpha=0.7,
                label=label,
            )
        # ax_violin.scatter(
        #     d,
        #     add_jitter(np.ones_like(d), jitter_factor),
        #     alpha=0.7,
        #     marker="o",
        #     s=2,
        #     c=colors[color_variable],
        # )
        ax_violin.set_yticks([1], labels=[values_dict[target_variable][idx]])
    h, l = ax_violin.get_legend_handles_labels()
    fig.legend(h, l, loc="outside upper right")
    fig.suptitle(target_variable)
    ax_big.set_xlabel("Difference from No Join")
    plt.tight_layout()


def violin_plot_with_hist(
    data, values_dict, label_mapping, target_variable, jitter_factor=0.05
):
    # Use the Set3 colormap for 4 distinct colors
    colors = plt.cm.Set1(np.arange(4))

    fig, axes = plt.subplots(
        nrows=1,
        ncols=4,
        sharey=True,
        gridspec_kw={"width_ratios": [2.5, 1, 2.5, 1]},
        figsize=(8, 5),
        layout="constrained",
    )
    ax_big = fig.add_subplot(111, frameon=False)
    # gs = GridSpec(1, 4, width_ratios=[3, 1, 3, 1])
    ax_big.spines["top"].set_color("none")
    ax_big.spines["bottom"].set_color("none")
    ax_big.spines["left"].set_color("none")
    ax_big.spines["right"].set_color("none")
    ax_big.tick_params(
        labelcolor="none", top=False, bottom=False, left=False, right=False
    )

    for idx, d in enumerate(data):
        ax_violin = axes[idx * 2]
        ax_hist = axes[idx * 2 + 1]

        parts = ax_violin.violinplot(d, showmedians=False, showmeans=False)
        ax_violin.set_xticks([1], labels=[values_dict[target_variable][idx]])
        quartile1, medians, quartile3 = np.percentile(d, [25, 50, 75])
        ax_violin.scatter(
            [1], medians, marker="o", color="white", s=30, zorder=3, edgecolors="black"
        )
        # ax_violin.hlines(medians, 0, 1)
        ax_violin.annotate(
            f"{medians:.2f}",
            xy=(-0.1, medians),
            xycoords=("axes fraction", "data"),
            size="x-small",
            color="blue",
        )
        ax_violin.axhline(medians, alpha=0.7, zorder=2, color="blue")

        color_variable = values_dict["est_cat"][idx]

        ax_violin.scatter(
            add_jitter(np.ones_like(d), jitter_factor),
            d,
            alpha=0.7,
            marker="o",
            s=5,
            c=colors[color_variable],
        )

        arrs = [
            np.array(d[values_dict["est_cat"][idx] == e_case])
            for e_case in label_mapping["idx"]
        ]
        h_colors = [colors[e_case] for e_case in label_mapping["idx"]]
        ax_hist.hist(
            arrs,
            bins=50,
            orientation="horizontal",
            histtype="stepfilled",
            color=h_colors,
            alpha=0.5,
            label=label_mapping["label"],
            # density=True,
            # weights=np.ones_like(subset)/len(subset),
            stacked=True,
        )
        h, l = ax_hist.get_legend_handles_labels()

        ax_violin.axhline(0, alpha=0.4, zorder=0, color="gray")
    fig.legend(h, l, loc="outside upper right")
    fig.suptitle(target_variable)
    ax_big.set_ylabel("Difference from No Join")
    # plt.tight_layout()


def prepare_case_subplot(
    ax,
    df,
    grouping_dimension,
    scatterplot_dimension,
    plotting_variable,
    kind="violin",
    xtick_format="percentage",
    jitter_factor=0.07,
    scatterplot_mapping=None,
    colormap_name="viridis",
    scatterplot_marker_size=3,
    average_folds="none",
    box_width=0.9,
    xmax=1,
):
    data = (
        df.select(grouping_dimension, plotting_variable)
        .group_by(grouping_dimension)
        .agg(pl.all(), pl.mean(plotting_variable).alias("sort_col"))
        .sort("sort_col")
        .drop("sort_col")
        .to_dict()
    )
    if scatterplot_mapping is None:
        scatterplot_mapping = prepare_scatterplot_labels(
            df, scatterplot_dimension, plotting_variable, colormap_name=colormap_name
        )

    if xtick_format in ["log", "symlog"]:
        ref_vline = 1
    else:
        ref_vline = 0

    ax.axvline(ref_vline, alpha=0.4, zorder=0, color="blue", linestyle="--")
    if kind == "violin":
        parts = ax.violinplot(
            data[plotting_variable],
            showmedians=False,
            showmeans=False,
            vert=False,
        )
        for pc in parts["bodies"]:
            pc.set_edgecolor("black")
            pc.set_facecolor("none")
            pc.set_alpha(1)
            pc.set_linewidth(1)
            pc.set_zorder(2.5)
    elif kind == "box":
        medianprops = dict(linewidth=2, color="red")
        boxprops = dict(linewidth=2)
        whiskerprops = dict(linewidth=2)
        capprops = dict(linewidth=2)
        boxprops = dict(facecolor="white")
        bp = ax.boxplot(
            data[plotting_variable],
            showfliers=False,
            vert=False,
            widths=box_width,
            medianprops=medianprops,
            boxprops=boxprops,
            whiskerprops=whiskerprops,
            capprops=capprops,
            zorder=2,
            patch_artist=True,
        )

    facecolors = ["grey", "white"]
    for _i, _d in enumerate(data[plotting_variable]):
        ax.axhspan(
            _i + 0.5, _i + 1.5, facecolor=facecolors[_i % 2], zorder=0, alpha=0.10
        )
        median = np.median(_d)
        ax.scatter(
            median,
            [_i + 1],
            marker="o",
            color="white",
            s=30,
            zorder=3.5,
            edgecolors="black",
        )
        y_scatter_pos = (
            np.linspace(-box_width / 2, box_width / 2, len(scatterplot_mapping))
        ) * 0.8
        for _, label in enumerate(scatterplot_mapping):
            this_label = LABEL_MAPPING[scatterplot_dimension][label]
            if _i > 0:
                this_label = "_" + this_label
            filter_dict = {
                scatterplot_dimension: label,
                grouping_dimension: data[grouping_dimension][_i],
            }
            values = df.filter(**filter_dict)[plotting_variable].to_numpy()
            ax.scatter(
                values,
                # _i + 1 + add_jitter(np.ones_like(values) * y_scatter_pos[_], 0.03),
                add_jitter(_i + np.ones_like(values), 0.1),
                color=scatterplot_mapping[label],
                marker="o",
                s=scatterplot_marker_size,
                alpha=0.7,
                label=this_label,
                zorder=2.5,
            )
    h, l = ax.get_legend_handles_labels()
    print(l)
    ax.set_yticks(
        range(1, len(data[grouping_dimension]) + 1),
        [LABEL_MAPPING[grouping_dimension][_l] for _l in data[grouping_dimension]],
    )

    ax = format_xaxis(ax, xtick_format, xmax)

    # xlim = ax.get_xlim()
    # ax.axvspan(xlim[0], 0, zorder=0, alpha=0.05, color="red")
    # ax.set_xlim(xlim)

    return h, l


def draw_split_figure(
    cases: dict,
    df: pl.DataFrame,
    split_dimension: str | None = None,
    grouping_dimensions: str | list[str] | None = None,
    scatterplot_dimension: str = "estimator",
    plotting_variable: str = "scaled_diff",
    kind: str = "violin",
    axes_formatting: dict = None,
    xtick_format: str = "percentage",
    colormap_name: str = "viridis",
    plot_label: str = None,
    figsize=(8, 3),
):
    if axes_formatting is None:
        axes_formatting = {
            "xaxis": {
                "xtick_format": "percentage",
                "xmax": 1,
                "logscale_base": 2,
            },
            "yaxis": {},
        }

    # Inner variables are all the variables that will be plotted, except the outer variable and the scatterplot variable
    if grouping_dimensions is None:
        grouping_dimensions = [
            _
            for _ in cases.keys()
            if (_ != split_dimension) & (_ != scatterplot_dimension)
        ]

    # Check that all columns are found
    assert all(_ in df.columns for _ in grouping_dimensions)
    if split_dimension is not None:
        assert split_dimension in df.columns
    assert scatterplot_dimension in df.columns
    assert plotting_variable in df.columns
    assert plotting_variable is not None

    if split_dimension is not None:
        n_cols = len(cases[split_dimension])
    else:
        n_cols = 1
    scatterplot_mapping = prepare_scatterplot_labels(
        df, scatterplot_dimension, plotting_variable, colormap_name
    )

    for idx_inner_var, case_inner_ in enumerate(grouping_dimensions):
        print(case_inner_)
        fig, axes = plt.subplots(
            nrows=1,
            ncols=n_cols,
            figsize=figsize,
            sharex=True,
            sharey="row",
            layout="constrained",
            squeeze=False,
        )

        if split_dimension is not None:
            for idx_outer_var, case_outer_ in enumerate(cases[split_dimension]):
                print("outer", case_outer_)
                ax = axes[0, idx_outer_var]
                subset = df.filter(pl.col(split_dimension) == case_outer_)

                h, l = prepare_case_subplot(
                    ax,
                    subset,
                    case_inner_,
                    scatterplot_dimension,
                    plotting_variable,
                    scatterplot_mapping=scatterplot_mapping,
                    xtick_format=xtick_format,
                    kind=kind,
                )
                axes[0][idx_outer_var].set_title(
                    LABEL_MAPPING[split_dimension][case_outer_]
                )
        else:
            ax = axes[0, 0]
            h, l = prepare_case_subplot(
                ax,
                df,
                case_inner_,
                scatterplot_dimension,
                plotting_variable,
                scatterplot_mapping=scatterplot_mapping,
                xtick_format=xtick_format,
                kind=kind,
            )
            # axes[0][0].set_title(
            #     LABEL_MAPPING[split_dimension][case_outer_]
            # )

        fig.legend(
            h,
            l,
            # loc="outside right",
            loc="outside lower left",
            mode="expand",
            ncols=len(l),
            markerscale=5,
            borderaxespad=-0.2,
            bbox_to_anchor=(0, -0.1, 1, 0.5),
            scatterpoints=1,
        )
        fig.set_constrained_layout_pads(
            w_pad=5.0 / 72.0, h_pad=4.0 / 72.0, hspace=0.0 / 72.0, wspace=0.0 / 72.0
        )
        # fig.suptitle(outer_dimension)
        if plot_label is not None:
            fig.supxlabel(plot_label)

        fig.savefig("test.pdf")
