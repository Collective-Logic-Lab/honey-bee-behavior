# bees_lifetimetracking_2018data
Run code on Binder:
[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/jacobdavidson/bees_lifetimetracking_2018data/HEAD)

Code and data to reproduce results in the paper:<br>
Smith, M. L., Davidson, J. D., Wild, B., Dormagen, D. M., Landgraf, T., and Couzin, I. D. (2022). The dominant axes of lifetime behavioral variation in honey bees. Submitted

Main analysis files descriptions:
- **'Fig1-IndividualExampleTrajectory.ipynb', 'FigsMain-Beeday-and-Beelife.ipynb','FigSupp-CombMaps.ipynb'**:  These contain all the plots and results in the paper, and can be run with the included data
- **Data Usage Example.ipynb**:  Contains simple, short example for reading in data


Other files:
- **beesgithub.yml, requirements.txt**:  Environment used for analysis, either to install with conda or pip
- **beeday-opentsne-train-1.pklz**: saving tSNE results so don't have to always recalculate 
- **datafunctions.py, definitions_2018.py, displayfunctions.py, all_cohorts.csv**:  Contain functions and definitions used in the analysis
- **definitions_2019.py, all_cohorts_2019.csv, summary_experiments_2019.csv**: Definitions and information for 2019 data
- **'Data processing - 1 - metrics and dataframes.ipynb', Data processing - 0 - database query.ipynb**:  Codes used to process data. 

The folder 'data2018' contains results needed to reprocedure figures and results in the paper. Full dataset, including x-y trajectories and behavioral metrics calculated at different timescales (per-hour,per-5 minute, per-1 minute), is available at Zenodo:  https://doi.org/10.5281/zenodo.6045859
