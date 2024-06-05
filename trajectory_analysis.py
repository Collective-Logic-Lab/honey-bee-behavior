# trajectory_analysis.py
#
# Bryan Daniels
# 2024/5/28
#
# Functions for analyzing bee trajectory data.
#

import numpy as np
import pandas as pd
import scipy.signal
import time_functions_2019 as tf

FRAMES_PER_SECOND = 3

# modified from
# https://swharden.com/blog/2020-09-23-signal-filtering-in-python/
def lowpass(data, cutoff: float, sample_rate: float,
    poles: int = 5):
    """
    Takes a pandas series, does linear interpolation to fill
    in missing values, drops nans at either end of the time
    series that can't be interpolated, applies a low pass
    filter, and returns datapoints only at timepoints that
    had data in the original series.
    """
    # set up filter
    sos = scipy.signal.butter(poles, cutoff, 'lowpass', fs=sample_rate, output='sos')

    # filter interpolated data
    interpolated_data = data.interpolate().dropna()
    filtered_data_array = scipy.signal.sosfiltfilt(sos, interpolated_data)

    # re-make into pandas series with NaNs at the same locations as in the original data
    filtered_data_series = pd.Series(filtered_data_array,index=interpolated_data.index)
    filtered_data_series[data.isna()] = np.nan
    
    return filtered_data_series

def add_low_pass_filter(t,cutoff=0.05,
    sample_rate=FRAMES_PER_SECOND):
    """
    Add low-pass filtered position data to a given trajectory
    dataFrame.  The input trajectory should be indexed by
    bee and time.  (see add_bee_time_index)
    
    Fills in any missing frame numbers with nans before
    applying the low-pass filter.
    
    cutoff (0.05)       : Cutoff frequency, in Hz
    sample_rate (3)     : Sample rate of data, in Hz
    
    """
    for bee in t.index.unique(level='uid'):
        # t_bee does not include data for every frame
        t_bee = t.loc[bee].copy()
        # t_bee_upsampled includes a row for every frame
        t_bee_upsampled = upsample(t_bee,sample_rate)
        
        # perform low-pass filter on upsampled data
        # and then drop the nans coming from upsampling
        x_filtered = lowpass(t_bee_upsampled['x'],
                        cutoff,sample_rate).dropna()
        y_filtered = lowpass(t_bee_upsampled['y'],
                        cutoff,sample_rate).dropna()
        
        # set index to match with t
        x_filtered.index = pd.Index(
            (bee,c) for c in x_filtered.index)
        y_filtered.index = pd.Index(
            (bee,c) for c in y_filtered.index)
        
        # add filtered data into the original trajectory t
        t.loc[bee,'filtered x'] = x_filtered
        t.loc[bee,'filtered y'] = y_filtered
    
def add_bee_time_index(t,frames_per_second=FRAMES_PER_SECOND):
    """
    Add MultiIndex to the given trajectory DataFrame, indexed
    first by bee ID and second by a DateTime object.
    
    Sorts the trajectory DataFrame by bee ID and time.
    """
    # compute datetimes from days and frame numbers
    timefunc = lambda row: tf.framenum_to_datetime(
        int(row['daynum']),row['framenum'],frames_per_second)
    t['time'] = t.apply(timefunc,axis=1)
    
    # set up bee,datetime MultiIndex
    t.set_index(['uid','time'], inplace=True)
    t = t.sort_index()
    
def upsample(t_bee,frames_per_second=FRAMES_PER_SECOND):
    """
    Returns trajectory for a single bee with missing
    frames inserted as NaNs.
    
    t_bee should be indexed by time only.
    
    Currently works only for 3 frames per second.
    """
    
    # should be given data for single bee, indexed by time
    assert(t_bee.index.name=='time')
    
    # currently only works for 3 frames per second
    assert(frames_per_second == 3)
    
    # need to be fancy here since 1/frames_per_second
    # is not an integer number of milliseconds...
    d_list = []
    d0 = t_bee.resample(
            tf.dt.timedelta(seconds=1),
                offset=tf.dt.timedelta(seconds=0/3)).asfreq()
    d1 = t_bee.resample(
            tf.dt.timedelta(seconds=1),
                offset=tf.dt.timedelta(seconds=1/3)).asfreq()
    d2 = t_bee.resample(
            tf.dt.timedelta(seconds=1),
                offset=tf.dt.timedelta(seconds=2/3)).asfreq()
    return pd.concat([d0,d1,d2]).sort_index()
        

def add_speed_data(t,pixels_per_cm=80,
    frames_per_second=FRAMES_PER_SECOND,max_delay_seconds=1,
    use_filtered=True):
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
    
    if use_filtered:
        x,y = t['filtered x'],t['filtered y']
    else:
        x,y = t['x'],t['y']
       
    # get bee ids, which may be in the trajectory's index
    if 'uid' in t.index.names:
        uids = t.reset_index(level='uid')['uid']
    else:
        uids = t['uid']
        
    t['delta x'] = np.concatenate([[np.nan],np.diff(x)])
    t['delta y'] = np.concatenate([[np.nan],np.diff(y)])
    t['delta framenum'] = np.concatenate([[np.nan],
                            np.diff(t['framenum'])])
    t['delta camera'] = np.concatenate([[np.nan],
                            np.diff(t['camera'])])
    t['delta uid'] = np.concatenate([[np.nan],
                            np.diff(uids)])

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


def state_matrix(df,col,divisions_per_day,df_type='behavioral'):
    """
    Takes a dataframe with specific columns, depending
    on `df_type`:
      - `Bee unique ID`, `Day number`, and `timedivision`
         if df_type = 'behavioral'
         (e.g. from a `df_day5min` file)
      - `uid`, `daynum`, `framenum`
         if df_type = 'trajectory'
         (e.g. from a `beetrajectories` file)
    
    Returns a dataframe indexed by bee id and with columns
    corresponding to time, with each element corresponding
    to the column `col` of the input dataframe.

    A given time division is included if (and only if) any
    data are available for that time division.
    A given bee is included if (and only if) any data are
    available for that bee at any time.

    divisions_per_day          : number of time divisions
                                 per day.  For df_type =
                                 'trajectory', this should
                                 typically be
                                 24*60*60*3 = 259200
                                 (for 3 frames per second)
    df_type ('behavioral')     : 'behavioral' or 'trajectory'
    """
    assert(type(col)==str)

    if df_type == 'behavioral':
        daycolumn = 'Day number'
        beecolumn = 'Bee unique ID'
        timecolumn = 'timedivision'
    elif df_type == 'trajectory':
        daycolumn = 'daynum'
        beecolumn = 'uid'
        timecolumn = 'framenum'
    else:
        raise(Exception,
            'Unrecognized df_type: {}'.format(df_type))
    
    # we will build lists of times and column_data
    column_data_list,times = [],[]
    
    days = df[daycolumn].unique()
    days.sort()
    # loop over days
    for daynum in days:
        df_day = df[df[daycolumn]==daynum]
        timedivisions = df_day[timecolumn].unique()
        timedivisions.sort()
        # loop over time divisions within a given day
        for timedivision in timedivisions:
            df_day_time = df_day[df_day[timecolumn]==timedivision]
            
            # construct column of data for the given time
            column_data_list.append(
                df_day_time.set_index(beecolumn)[col] )

            # convert time division to an absolute time
            times.append(tf.timediv_to_datetime(
                int(daynum),timedivision,divisions_per_day))
            
    return pd.DataFrame(column_data_list,index=times).T
