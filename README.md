Benchmarking Join Suggestions
===

This repository contains the code used to run a benchmark on join suggestion algorithms.

Datasets are sourced from d3m and augmentation candidates are obtained using Auctus. 
The downstream performance is tested using the ML tasks reported in the metadata provided
by d3m. 

Given the augmentation candidates, additional candidates are generated by creating
new, redudant versions of the already known datasets. This is done to reflect 
real-life data analysis operations and table augmentations. 

# Scripts
`main_dataprep.py` is used to prepare the candidate set given a list of datasets. 
`target_datasets.txt` contains a list of all datasets that include only tabular data.
`targets_datasets_small.txt` contains one dataset for each type of downstream task. 



# Reference links

## D3M/Auctus/datamart
- [D3M dataset repository](https://datasets.datadrivendiscovery.org/d3m/datasets)
- [D3M metadata documentation](https://gitlab.com/datadrivendiscovery/data-supply/-/tree/shared/documentation)
- [datamart rest API](https://datadrivendiscovery.gitlab.io/datamart-api/python.html#python-api)
- [D3M developer documentation](https://docs.datadrivendiscovery.org/devel/index.html)
- [Auctus documentation](https://docs.auctus.vida-nyu.org/index.html)

## Logging
- [mlflow](https://mlflow.org)
