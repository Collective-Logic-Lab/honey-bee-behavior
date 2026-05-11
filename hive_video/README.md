## Hive Video

This directory is home to tools for pre-processing and analysis of honey bee hive video data. Here, we are working with data from "Videos for honey bee lifetime tracking data 2019" published by Smith, et al. (2019) with a referenced related article by Neubauer et al. (2023), "Honey Bee Drones Are Synchronously Hyperactive inside the Nest." DOIs are [10.17617/3.LLWRWR](https://doi.org/10.17617/3.LLWRWR) (dataset) and [10.1016/j.anbehav.2023.05.018](https://doi.org/10.1016/j.anbehav.2023.05.018) (paper).

### Getting started

To get started, you'll typically clone the overall repository. **Important note:** for working with the Video tools, it will be by far the most convenient to set the working directory to `./hive_video`. We recommend the use of a virtual environment for development, and this documentation is written assuming the use of `uv` for managing dependencies.

An example path might be:

```bash
git clone https://github.com/collab-bees/honey-bee-behavior.git
cd honey-bee-behavior/hive_video
# so, `pwd` would return `[your-workspace]/honey-bee-behavior/hive_video`

uv venv
source .venv/bin/activate
uv sync
```
... the packages and the data acquisition scripts should now be ready to use.

The project ships with a small amount of seed data in in the `hive_video/data/` directory. A thirty second sample video is included in `video/data/raw/` in the file `starter_video.mp4`. The `video/data/experiments/` directory contains the output of a sample pipeline run on that video. More information for working with these is included in the `docs/getting_started.ipynb` notebook. 

### Getting Data

This repository works with large video files. For most of the work to be done, you'll need to sync be able to access and sync with the public Collective Logic Lab HuggingFace data bucket, `collective-logic-lab/honey-bee`. The repository packaging includes the HuggingFace CLI, `hf`, and it is referenced in our pre-packaged scripts. You can also run `hf` as separately installed on your system or in your Python environment; for example, `uvx hf sync ...`. Since the bucket is public, a login is not required to download the data.

We package video data as "distributions" for download. Currently, a great way to get started is to work with our `base-distribution`, which will be continuously updated. We have included a short script, `get_base_dist.py`. So:

```bash
uv run python get_base_dist.py
```

... will deliver files to each of the `data/artifacts/`, `data/experiments/`, and `data/raw/` directories. The files in the base distribution are selected as a representative and interesting slices of the overall video repository.