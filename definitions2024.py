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

## Number of visits to the dance floor (df is beeTraj)!!
def numOfDanceFloorVisitsTOTAL(df):
    dance = df.groupby(['uid','daynum'])['cross_df'].sum().to_frame(name='df_visits').reset_index()
    df = pd.merge(df,dance, on=['uid','daynum'], how='left')
    
    return df

def numOfDanceFloorVisitsRUNNINGTOTAL(df):
    df = df.sort_values(by=['uid', 'daynum'])
    
    df['prev_cross_df'] = df.groupby(['uid'])['cross_df'].shift(1)
    df['transitions'] = ((df['prev_cross_df'] == 0) & (df['cross_df'] == 1)).astype(int)
    visits_total = df.groupby(['uid','daynum'])['transitions'].sum().reset_index(name='visits_total')
    
    df = pd.merge(df, visits_total, on=['uid', 'daynum'], how='left')
    
    df['running_total_df_visits'] = df.groupby('uid')['transitions'].cumsum()
    df = df.drop(columns=['prev_cross_df', 'transitions', 'visits_total'])
    
    return df

#beeTraj MUST have running_total_df_visits
def numOfDanceFloorVisits(leave, beeTraj, frames):
    # beeTraj to dict
    traj_dict = {(uid, daynum): group.set_index('framenum')['running_total_df_visits']
                 for (uid, daynum), group in beeTraj.groupby(['uid', 'daynum'])}
    
    rolling_visits = []

    #group by bee and day
    for (uid, daynum), group in leave.groupby(['uid', 'daynum']):
        if (uid, daynum) not in traj_dict:
            rolling_visits.extend([np.nan] * len(group))
            continue
        
        bee_traj = traj_dict[(uid, daynum)]
        
        # for each row in current bee and day group
        curr_frames = group['framenum'].values
        curr_visits = group['running_total_df_visits'].values  # current frame's total number of df visits
        start_frames = curr_frames - frames  #start frame numbers
        
        # find closest available frame
        available_frames = bee_traj.index.values
        idxs = np.searchsorted(available_frames, start_frames, side='left')
        idxs = np.clip(idxs, 0, len(available_frames) - 1)  #index check
        
        # number of visits at start
        start_visits = bee_traj.iloc[idxs].values  #get start frame visit counts
        
        # calculate number of visits in between
        recent_visits = curr_visits - start_visits
        rolling_visits.extend(recent_visits)
    
    rolling_visits = np.array(rolling_visits)

    #add result to dataframe
    leave.loc[:, 'recent_df_visits'] = rolling_visits
    return leave

## Hardcoded 5 minute bounds for convinience
def get5MinBounds(time):
    lower = int(time - 900) 
    upper = int(time + 900)
    return upper,lower

def getPlottingEvent(daynum, beeTraj, frame, beeID, framesBefore, framesAfter):
    
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

def getPlottingEvent(daynum, beeTraj, frame, beeID, framesBefore, framesAfter):
    
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



