## Hive Video

Honey bee hives are busy, layered, and difficult to read frame by frame. This folder contains tools for turning long hive videos into research-friendly artifacts: resequenced videos, motion-regime overlays, experiment outputs, and notebooks for reviewing collective behavior in the hive.

The current work focuses on comb-building and festoon-related behavior in the "Videos for honey bee lifetime tracking data 2019" dataset published by Smith et al. (2019), with related context from Neubauer et al. (2023), "Honey Bee Drones Are Synchronously Hyperactive inside the Nest." DOIs: [10.17617/3.LLWRWR](https://doi.org/10.17617/3.LLWRWR) for the dataset and [10.1016/j.anbehav.2023.05.018](https://doi.org/10.1016/j.anbehav.2023.05.018) for the paper.

The videos are here: [https://edmond.mpg.de/dataset.xhtml?persistentId=doi:10.17617/3.LLWRWR](https://edmond.mpg.de/dataset.xhtml?persistentId=doi:10.17617/3.LLWRWR).

Edmonds runs Dataverse. There is a schematic image for download at [https://doi.org/10.17617/3.LLWRWR](this location).

### TLDR

Run this from the repository root to set up the video tools:

```bash
cd hive_video
uv venv
source .venv/bin/activate
uv sync
uv run python get_dist_1.py
```

Then open `docs/experiments.ipynb`. The repository already includes a small five second sample video, and `get_dist_1.py` downloads the larger resequenced video artifact plus selected experiment outputs used by the notebook.

### Getting started

To get started, clone the overall repository and work from `./hive_video`. We recommend a virtual environment, and this documentation assumes `uv` for dependency management.

An example path might be:

```bash
git clone https://github.com/collab-bees/honey-bee-behavior.git
cd honey-bee-behavior/hive_video
# so, `pwd` would return `[your-workspace]/honey-bee-behavior/hive_video`

uv venv
source .venv/bin/activate
uv sync
```

The packages and data acquisition scripts should now be ready to use.

The project ships with a small amount of seed data in the `hive_video/data/` directory. A five second sample video is included in `data/raw/start04_sample_5s.mp4`, and `data/experiments/experiment_example_5s/` contains the output of a sample pipeline run on that video. Larger artifacts are distributed separately.

### Getting Data

This repository works with large video files. For most of the work to be done, you'll need to sync be able to access and sync with the public Collective Logic Lab HuggingFace data bucket, `collective-logic-lab/honey-bee`. The repository packaging includes the HuggingFace CLI, `hf`, and it is referenced in our pre-packaged scripts. You can also run `hf` as separately installed on your system or in your Python environment; for example, `uvx hf sync ...`. Since the bucket is public, a login is not required to download the data.

We package larger video data as named distributions for download. The first curated distribution contains the resequenced video artifact and representative experiment outputs used by `docs/experiments.ipynb`. It does not include `data/raw/start04_sample_5s.mp4` or `data/experiments/experiment_example_5s/`, because those are tracked directly in Git.

To download Distribution 1 into the paths expected by the notebooks:

```bash
uv run python get_dist_1.py
```

This syncs distribution files into `data/artifacts/` and `data/experiments/`. Distribution 1 includes only selected outputs from the larger Experiment 3 overnight parameter sweep: runs 09, 11, and 16, plus the summary figure and metric tables. The full overnight sweep can remain available in the data bucket as an archive without being part of the default download.

### Organization

The `src` folder has two major submodules and two helper folders. First, the hive videos that we are working with are archived in a disordered state: the sequence of frames cuts to a different part of the video every few minutes. The `resequence` module contains code that applies one algorithm to isolate the individual video segments, and a second algorithm to process those segments into the best identifiable working order. 

The `analyze` module contains code that attempts to classify and visually separate the bee behaviors in the video.
