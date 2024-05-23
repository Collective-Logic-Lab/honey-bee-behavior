# time_functions_2019.py
#
# Bryan Daniels
# 2024/5/23
#
# Some useful functions for dealing with times in the
# bee data.
#
# Currently uses definitions for 2019 data.
#

import datetime as dt
from bees_drones_2019data import definitions_2019 as bd

FRAMES_PER_SECOND = 3

def framenum_to_datetime(daynum,framenum,
    frames_per_second=FRAMES_PER_SECOND):
    return bd.alldaytimestamps[daynum] + dt.timedelta(seconds=framenum/frames_per_second)
    
def seconds_past_midnight(datetime):
    return (datetime - datetime.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds()
    
def datetime_to_framenum(datetime,
                         frames_per_second=FRAMES_PER_SECOND):
    return int(np.floor(
        seconds_past_midnight(datetime)*frames_per_second))

def timediv_to_datetime(daynum,timediv,divisions_per_day):
    assert(timediv < divisions_per_day)
    return bd.alldaytimestamps[daynum] + dt.timedelta(days=timediv/divisions_per_day)
    
def datetime_to_daynum(datetime):
    date_list = [str(ts.date()) for ts in bd.alldaytimestamps]
    return date_list.index(str(datetime.date()))
