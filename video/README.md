## Video

This directory is home to tools for pre-processing and analysis of honey bee hive video data. Here, we are working with data from "Videos for honey bee lifetime tracking data 2019" published by Smith, et al. (2019) with a referenced related article by Neubauer et al. (2023), "Honey Bee Drones Are Synchronously Hyperactive inside the Nest." DOIs are [10.17617/3.LLWRWR](https://doi.org/10.17617/3.LLWRWR) (dataset) and [10.1016/j.anbehav.2023.05.018](https://doi.org/10.1016/j.anbehav.2023.05.018) (paper).

### Getting started

To get started, you'll need to clone this repository, which comes with a small starter video in the _raw directory. We recommend the use of a virtual environment for development, and this documentation is writted assuming the use of `uv` for managing dependencies. Once you clone the repo, for instance, you can issue:

```bash
uv venv
source .venv/bin/activate
uv sync
```

... and both the packages and data acquisition scripts should now be ready to use.

You can test the working operation of the analysis pipeline using the included notebook, docs/getting_started.ipynb. 

This repository works with large video files. For most of the work to be done, you'll need to sync be able to access and sync with the public Collective Logic Lab HuggingFace data bucket, `collective-logic-lab/honey-bee`. The repository packaging includes the HuggingFace CLI, `hf`, and it is referenced in our pre-packaged scripts. You can also run `hf` as separately installed on your system or in your Python environment; for example, `uvx hf sync ...`. Since the bucket is public, a login is not required to download the data.

