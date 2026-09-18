# `envs/`

This folder contains shared configurations and instructions for running the code in this repository on environments outside of a workstation. At this time the one environment we are documenting is the [ASU Sol Supercomputer](https://docs.rc.asu.edu/supercomputer-hardware) and its [recommended Mamba package manager](https://docs.rc.asu.edu/mamba).

## Setup on Sol

### Connect to Sol

Developers with a Sol account and access to the `grp_bdaniel6` group can use the shared environment. The [ASU connection instructions](https://docs.rc.asu.edu/connecting/) cover VPN and login setup. A terminal is available through the [Sol web portal](https://sol.asu.edu) or an SSH connection; the commands below run in that Sol terminal.

### Clone your fork into your workspace

Developers can clone their forks of [honey-bee-behavior](https://github.com/Collective-Logic-Lab/honey-bee-behavior) and into a personal workspace on Sol, following [CONTRIBUTING.md](../CONTRIBUTING.md). This example uses `~/workspace`. Replace `YOUR_GITHUB_USERNAME` with your GitHub username, which *may differ from your ASURITE ID*:

```bash
mkdir -p ~/workspace
cd ~/workspace
git clone https://github.com/YOUR_GITHUB_USERNAME/honey-bee-behavior.git
cd honey-bee-behavior
git remote add upstream https://github.com/Collective-Logic-Lab/honey-bee-behavior.git
```

This sets the fork as `origin` and the lab repository as `upstream`. An existing checkout on Sol works too. Developers can create branches in their forks for changes and contribute through pull requests, as described in the contributing guide.

`~/workspace/honey-bee-behavior` holds the code checkout, and `/data/grp_bdaniel6/envs` holds the shared Python environment. Data access is configured separately for each workflow. Project storage and temporary scratch space are available for large datasets and analysis outputs; the [ASU storage guidance](https://docs.rc.asu.edu/file-system-overview/) describes their uses.

## Working on Sol

Developers can activate the shared environment at `/data/grp_bdaniel6/envs/honey-bee-behavior-v1` and use its installed packages with their own repository checkout.

**Validation:** Sol validation details (date, code revision, and tested workflows) have not yet been recorded here.

### Activate and check

For a quick check of an existing environment, developers can request a basic compute allocation with:

```bash
interactive
```

For environment creation, developers can use the larger allocation [below](#creating-the-shared-environment). Analysis jobs can request resources suited to their workload.

Within that allocation, these commands enter the checkout and load the environment using the [ASU Mamba instructions](https://docs.rc.asu.edu/mamba/). Adjust the checkout path if needed:

> **Note** as of September 14 we are still working on the shared folder listed below. For the moment this path is not available and you have to build your own env as described below.

```bash
cd ~/workspace/honey-bee-behavior
module load mamba/latest
source activate /data/grp_bdaniel6/envs/honey-bee-behavior-v1
```

From the checkout root, developers can check the environment with:

```bash
python envs/sol/confirm_env_sol.py
```

The script reports the Python executable and environment path, checks imports and package dependencies, writes and reads a tiny HDF5 table, renders a plot without a display, and checks that FFmpeg, FFprobe, and GitHub CLI (`gh`) start. It uses temporary files and exits with a nonzero status if a check fails. The GitHub CLI check does not require a login. Passing these checks does not establish that every notebook or analysis works.

Activation applies to the current shell, so each new terminal or Slurm job needs the module and activation commands before running Python. An existing compute allocation works without another `interactive` request.

### Set up GitHub CLI

The recipe includes [GitHub CLI (`gh`) from conda-forge](https://anaconda.org/conda-forge/gh) for workshop and contribution tasks. After activating the environment, developers can authenticate from their own Sol accounts and configure Git to use that login for HTTPS operations:

```bash
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git --hostname github.com
gh auth status --hostname github.com
```

Follow the [browser login instructions](https://cli.github.com/manual/gh_auth_login) printed by `gh`; the URL and one-time code can be opened in a browser on your own computer. The CLI installation is shared, while each developer's authentication is stored separately under their Sol account. The [`setup-git` command](https://cli.github.com/manual/gh_auth_setup-git) configures Git's credential helper; the fork and upstream remotes remain as described above.

An environment built before `gh` was added to the recipe needs a maintainer update or a new build before these commands are available.

### Use notebooks

After activating the environment, developers can register it as a Jupyter kernel for their own account. Registration is a one-time step for each environment version:

```bash
python -m ipykernel install --user \
  --name honey-bee-behavior-v1 \
  --display-name "Honey Bee Behavior (v1)"
```

The kernel is then available as **Honey Bee Behavior (v1)** in Jupyter on the [Sol web portal](https://sol.asu.edu). This follows ASU's [instructions for kernels in a `/data` directory](https://docs.rc.asu.edu/jupyter-kernels/#creating-kernels-from-a-data-directory); `ipykernel` is already included in the recipe.

With shared dependencies already installed, developers can skip package-installation cells such as the editable installation in `notebooks/hive-video-examples.ipynb`. Code changes stay in the personal checkout. For different dependencies, developers can create a separate environment or propose an update to this recipe.

## Creating the shared environment

Developers maintaining a shared installation can build it from the files in [sol/](sol/):

| File | Purpose |
| --- | --- |
| [sol.yml](sol/sol.yml) | Python, scientific libraries, notebook tools, GitHub CLI, and native video dependencies from conda-forge. |
| [sol-pip-requirements.txt](sol/sol-pip-requirements.txt) | The two pinned, hashed wheels installed after Mamba. |
| [confirm_env_sol.py](sol/confirm_env_sol.py) | A small environment check for an activated installation. |

A shared installation needs a writable destination under `/data/grp_bdaniel6/envs` and group access to read and traverse that path. Building at the final location preserves the absolute paths in a Mamba environment. The example below creates `honey-bee-behavior-v1`; if that path already exists, use a new version name throughout the commands so existing analyses retain their current dependencies.

Developers can request 4 CPU cores, 32 GB of total memory, and one hour for the build, following the [ASU resource request guidance](https://docs.rc.asu.edu/requesting-resources/). Environment creation has run out of memory during package linking in a default allocation, even after dependency resolution succeeded. The following request provides more headroom for installation and runs from a login-node shell:

```bash
interactive -c 4 --mem=16G -t 01:00:00
```

After an out-of-memory failure, developers can leave the previous allocation and request a new one with these settings. An interrupted installation can leave a partial environment; rebuilding into an unused prefix and running the confirmation script avoids relying on that partial installation.

Once the allocation starts, these commands run from the checkout root. Each step depends on the previous step succeeding:

```bash
module load mamba/latest
mkdir -p /data/grp_bdaniel6/envs
mamba env create \
  --prefix /data/grp_bdaniel6/envs/honey-bee-behavior-v1 \
  --file envs/sol/sol.yml
source activate /data/grp_bdaniel6/envs/honey-bee-behavior-v1
python -m pip install --no-deps --require-hashes --only-binary=:all: \
  -r envs/sol/sol-pip-requirements.txt
python envs/sol/confirm_env_sol.py
```

Mamba supplies NumPy, OpenCV, Pillow, FFmpeg, and the other shared dependencies. Pip installs only `hive-video` and `portable-ffmpeg`, using the published wheel hashes. The `--no-deps` option keeps pip from replacing Mamba's packages. The `hive-video` resequencing dependencies are already in `sol.yml`, so there is no need to install its `[resequence]` extra. FFmpeg and FFprobe should come from the activated environment's `bin` directory.

Developers can validate a candidate environment by loading a small slice of bee data, running a representative analysis, and processing a short video clip. Running the confirmation script from another group account also checks shared access. Maintainer-only write access keeps the installed packages stable, while group read, directory traversal, and executable access allow shared use. Research data and outputs belong outside the environment directory.

After validation, the exact Linux package builds can be saved from the activated environment:

```bash
mamba list --explicit --md5 > envs/sol/sol-linux-64.explicit.txt
```

Developers can include that generated file in a contribution alongside the recipe and pip requirements, and update the validation note above with the environment path, date, code revision, and workflows checked. The explicit file records the conda packages; the separate pip requirements are still needed. The recipe alone can resolve to newer package builds on a later date.

For dependency changes, developers can build and validate a new version such as `honey-bee-behavior-v2`, then update the documented path and kernel name. Keeping the old version available lets existing work finish with its original dependencies. Editable installations of personal repository clones fit in separate development environments.

## Dependency scope

This recipe covers the scientific libraries used here, video work with [hive-video 0.1.1](https://pypi.org/project/hive-video/0.1.1/), and the additional widgets/FFmpeg needs found in [Bee-Data-Analysis](https://github.com/Shatadru-Saha/Bee-Data-Analysis). It targets Python 3.12 to meet `hive-video`'s minimum Python version. The legacy requirements and the incoming repository's workstation package list are not Sol installation instructions. `openTSNE` and the historical PostgreSQL query dependencies are outside this initial recipe.

Some code still needs separate cleanup: older notebooks use removed pandas APIs such as `DataFrame.append`; imports such as `bees_drones_2019data` and `toolbox` refer to missing local modules; and several analyses assume particular working directories or data paths. The incoming festooning notebook also uses `%matplotlib qt`, which needs adjustment for browser notebooks or jobs without a display. These are code and data-configuration issues to resolve as we establish supported workflows.
