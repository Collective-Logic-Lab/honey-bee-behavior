import numpy as np
import pandas as pd

## Adds "in_exit_frame" column to dataframe. df = your dataframe, pix = bd.xpixels from definitions_2018
def getExitFrameLocation(df, pix):
    #hardcoded!!
    x_max = 6500
    x_min = 3500
    y_min = 3800
    y_max = 5400
    
    x = np.array(df['x']).astype(float)
    y = np.array(df['y']).astype(float)
    camera = np.array(df['camera']).astype(int)
    conv_factor = 1
    x_adjusted = x/conv_factor + (np.logical_not(camera).astype(int))*pix
    y_adjusted = y/conv_factor

    
    x_bounds = (x_adjusted >= x_min) & (x_adjusted <= x_max)
    y_bounds = (y_adjusted >= y_min) & (y_adjusted <= y_max)
    
    df['in_exit_frame'] = (x_bounds & y_bounds).astype('int')
    
    return df

## Adds "cross_df" column to dataframe. df = your dataframe, pix = bd.xpixels from definitions_2018
def crossedDanceFloor(df, pix):
    x_max = 6000
    x_min = 4700
    y_min = 4350
    y_max = 5200
#     dance_floor={'top':4350,'bottom':5200,'right':6000,'left':4700}
    x = np.array(df['x']).astype(float)
    y = np.array(df['y']).astype(float)
    camera = np.array(df['camera']).astype(int)
    conv_factor = 1
    x_adjusted = x/conv_factor + (np.logical_not(camera).astype(int))*pix
    y_adjusted = y/conv_factor

    
    x_bounds = (x_adjusted >= x_min) & (x_adjusted <= x_max)
    y_bounds = (y_adjusted >= y_min) & (y_adjusted <= y_max)
    
    df['cross_df'] = (x_bounds & y_bounds).astype('int')
    
    return df

## Number of visits to the dance floor
def numOfDanceFloorVisits(df):
    dance = df.groupby(['uid','daynum'])['cross_df'].sum().to_frame(name='df_visits').reset_index()
    df = pd.merge(df,dance, on=['uid','daynum'], how='left')
    
    return df

## Hardcoded 5 minute bounds for convinience
def get5MinBounds(time):
    lower = int(time - 900) 
    upper = int(time + 900)
    return upper,lower



## Creates dataframe based on given day and adds available information.
def getBeeTraj(daynum):
    if daynum >= 50:
        datadir = PATH + 'beetrajectories_days_050_to_085/'
    else:
        datadir = PATH + 'beetrajectories_days_000_to_049/'
    
    beeTrajectoriesByFrame = pd.read_hdf('{}beetrajectories_{:0>3}.hdf'.format(datadir,daynum)) #data per frame in which each bee was seen
    beeTrajectoriesByFrame = getExitDist(beeTrajectoriesByFrame)
    return beeTrajectoriesByFrame

def getHiveEvents(daynum):
    # boolInHiveByIDByTime into dataframe ----------------------------------------------------
    inHive = pd.DataFrame(boolInHiveByIDByTime)
    inHive = inHive.T #transpose so rows = time and cols = uid
                                
    #get hive statuses by taking difference on axis 0 (rows, which represent time)
    hive_statuses_list = np.diff(inHive, axis = 0) # TODO document code
    #print(len(hive_statuses_list[1])) #PRINT CHECK (len 1439, len of each is 1435)
    
    # translate time to framenum (assuming 3 frames per second)-------------------------------
    frames_per_day = 24*60*60*3
    frames_per_timedivision = frames_per_day / numtimedivs
    
    """
    inHive['index'] = range(len(inHive))
    inHive['minsPastMidnight'] = inHive['index']*1 #bin size = 1min (see datafunctions.py), TODO un-hardcode
    
    
    inHive['framenum'] = inHive['index']*frames_per_timedivision
    """
    
    hive_statuses_by_uid = []
    
    #return [i for i in zip(day_uids,hive_statuses_list)]
    
    hive_statuses_list = np.transpose(hive_statuses_list) # First index is beeUID, second is minute
    for uid, hive_statuses in zip(day_uids,hive_statuses_list):
        for hive_status in hive_statuses:
            hive_statuses_by_uid.append([uid,hive_status])
    df_hive_events = pd.DataFrame(hive_statuses_by_uid,columns=['uid','diff'])
    df_hive_events['index'] = range(len(df_hive_events))
    
    #minutes and framenum columns---------------------------------------------------------------
    result = []
    numEntriesPerUid = len(df_hive_events[df_hive_events['uid'] == df_hive_events['uid'].iat[0]])
    for value in df_hive_events['index']:
        result.append(value % numEntriesPerUid)
    df_hive_events['min'] = result
    
    df_hive_events['framenum'] = df_hive_events['min']*frames_per_day/(24*60)
    
    df_hive_events = df_hive_events[['index', 'uid', 'diff', 'min', 'framenum']]
    
    #stauses--------------------------------------------------------------------------------------
    conditions = [
        (df_hive_events['diff'] == -1.0),
        (df_hive_events['diff'] == 1.0),
        (df_hive_events['diff'] == 0.0),
    ]
    choices = ['leave', 'return', 'no change']
    df_hive_events['status'] = np.select(conditions, choices, default='not sure')
    
    """
    for plotting purposes, single out rows in beetraj df and surrounding rows to track data.
    
    add function to do exit distance and num dance floor visits for selected rows (new df)
    """
    
    return df_hive_events

def getPlottingEvent(daynum, frame, beeID, framesBefore, framesAfter):
    beeTraj = getBeeTraj(daynum)
    
    #filter data to just the one bee
    filteredBee = beeTraj[beeTraj['uid']==beeID]
    
    # set desired range of frames
    minFrame = frame - framesBefore #recommended frames before: 1800 (10 minutes), frames after: 50 (just to see the bee is back)
    maxFrame = frame + framesAfter
    plottingEvents = pd.DataFrame()
    
    #filtering for desired frames of the bee's data
    filtered_rows = filteredBee[(filteredBee['framenum'] >= minFrame) & (filteredBee['framenum'] <= maxFrame)]

    #adding filtered rows to resulting dataframe
    plottingEvents = pd.concat([plottingEvents, filtered_rows], ignore_index=True)

    #finding largest gap between frames to place line. frameNew = REAL FRAME OF LEAVING
    distBetweenFrames = plottingEvents['framenum'].diff()
    start = distBetweenFrames.dropna().idxmax()-1
    frameNew = plottingEvents['framenum'][start]+1
    
    ##REPEAT CODE TO CENTER AROUND LEAVING FRAME----------------------
    minFrame = frameNew - framesBefore #recommended frames before: 1800 (10 minutes), frames after: 50 (just to see the bee is back)
    maxFrame = frameNew + framesAfter
    plottingEventsNEW = pd.DataFrame()
    
    #filtering for desired frames of the bee's data
    filtered_rows = filteredBee[(filteredBee['framenum'] >= minFrame) & (filteredBee['framenum'] <= maxFrame)]

    #adding filtered rows to resulting dataframe
    plottingEventsNEW = pd.concat([plottingEventsNEW, filtered_rows], ignore_index=True)
    #------------------------------------------------------------------
    
    #finding bee disappearance
    frameGone = filteredBee['framenum'].iloc[-1]
    
    #if the bee does not return, frameReturn = -1
    if(frameGone != frameNew):
        frameReturn = plottingEvents['framenum'][start+1]
    else:
        frameReturn = -1
        
    print("Leave: ", frameNew)
    print("Return: ", frameReturn)
    print("Disappears: ", frameGone)
    
    return plottingEventsNEW, frameNew, frameReturn, frameGone



