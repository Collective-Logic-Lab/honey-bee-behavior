# bees_lifetimetracking_2018data

Code and data to reproduce results in the paper:<br>
Smith, M. L., Davidson, J. D., Wild, B., Dormagen, D. M., Landgraf, T., and Couzin, I. D. (2021). The dominant axes of lifetime behavioral variation in honey bees. bioRxiv, 2021.04.15.440020. doi:10.1101/2021.04.15.440020.
https://www.biorxiv.org/content/10.1101/2021.04.15.440020v1

File descriptions:

- **Data Usage Example.ipynb**:  Contains simple, short example for reading in data
- **bees2.yml**:  Conda environment used for analysis
- **datafunctions.py, definitions_2018.py, displayfunctions.py, all_cohorts.csv**:  Contain functions and definitions used in the analysis
- **'1 - DBquery.ipynb', '2 - Create data matrix.ipynb'**:  Codes used to process data.  These need database access and detailed results output.
- **'3 - Overall trends and substrate use.ipynb', '4 - Bee-day analysis.ipynb'**:  These contain all the plots and results in the paper, and can be run with the included data in 'savedresults'

Added - additional data example
- **Data Usage Example-2019.ipynb**:  Contains simple, short example for reading in a subset of data taken in 2019
