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



