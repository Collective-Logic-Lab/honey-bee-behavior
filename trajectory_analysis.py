# trajectory_analysis.py
#
# Bryan Daniels
# 2024/5/28
#
# Functions for analyzing bee trajectory data.
#

import numpy as np

FRAMES_PER_SECOND = 3

def add_speed_data(t,pixels_per_cm=80,
    frames_per_second=FRAMES_PER_SECOND,max_delay_seconds=1,):
    """
    Adds speed data to a given trajectory dataFrame.

    Note: Assumes trajectory data is sorted in time order
    for each bee!

    max_delay_seconds (1)     : Do not compute speeds for
                                \Delta t > max_delay_seconds
                                (as in bees_drones_2019data/
                                 Data processing - 1 - metrics
                                 and dataframes.ipynb/
                                 Data processing to calculate
                                 metrics)
    """
    
    t['delta x'] = np.concatenate([[np.nan],np.diff(t['x'])])
    t['delta y'] = np.concatenate([[np.nan],np.diff(t['y'])])
    t['delta framenum'] = np.concatenate([[np.nan],
                            np.diff(t['framenum'])])
    t['delta camera'] = np.concatenate([[np.nan],
                            np.diff(t['camera'])])
    t['delta uid'] = np.concatenate([[np.nan],
                            np.diff(t['uid'])])

    # remove cases of different bees (note: unlikely not to
    # already be caught by the time delay filter below?)
    t.loc[t['delta uid'] != 0, ['delta x',
                                'delta y',
                                'delta framenum',
                                'delta camera',
                                'speed (cm/s)']] = np.nan
    
    # compute speeds
    t['speed (cm/s)'] = np.linalg.norm(
        [t['delta x'],t['delta y']],axis=0)/pixels_per_cm \
        / (t['delta framenum']/frames_per_second)
    
    # implement maximum time delay (as in bees_drones_2019data)
    t.loc[t['delta framenum']/frames_per_second > max_delay_seconds,'speed (cm/s)'] = np.nan

    # remove cases in which the bee is observed across
    # different cameras (as in bees_drones_2019data)
    t.loc[t['delta camera'] != 0, 'speed (cm/s)'] = np.nan
