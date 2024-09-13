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
    visits_total = df.groupby(['uid', 'daynum'])['transitions'].sum().reset_index(name='visits_total')
    
    df = pd.merge(df, visits_total, on=['uid', 'daynum'], how='left')
    
    df['running_total_df_visits'] = df.groupby('uid')['transitions'].cumsum()
    df = df.drop(columns=['prev_cross_df', 'transitions', 'visits_total'])
    
    return df
'''
#df is leave
def numOfDanceFloorVisits(df, beeTraj, frames):
    df['df_visits'] = 0
    
    #group by bee and day
    for (uid, daynum), group in df.groupby(['uid', 'daynum']):
        rolling_visits = []
        
        #for each row in current bee and day group
        for i in range(len(group)):
            
            curr_frame = group.iloc[i]['framenum'] # current frame number
            curr_visits = numOfDanceFloorVisitsTOTAL(df[df['framenum']<curr_frame]) # current frame's total number of df visits
            start_frame = curr_frame - frames # desired start frame number
            
            startExists = ((beeTraj['framenum'] == start_frame) & 
                            (beeTraj['uid'] == group.iloc[i]['uid']) & 
                            (beeTraj['daynum'] == group.iloc[i]['daynum'])).any()
            
            #if desired start frame does not exist!
            if not startExists:
                print("start doesnt exist")
                # if start frame is not there, use next most recent frame
                possible = (beeTraj['uid'] == group.iloc[i]['uid']) & (beeTraj['daynum'] == group.iloc[i]['daynum']) & (beeTraj['framenum'] > (curr_frame - frames))
                        
                start_frame = beeTraj[possible]['framenum'].min()
                print(start_frame)
            
            # number of visits at start
            start_visits_df = beeTraj[(beeTraj['framenum'] == start_frame) &
                                    (beeTraj['uid'] == group.iloc[i]['uid']) &
                                    (beeTraj['daynum'] == group.iloc[i]['daynum'])]
            
            if not start_visits_df.empty:
                start_visits = start_visits_df['df_visits'].values[0]
            else:
                start_visits = 0
                            
            # calculate number of visits in between
            recent_visits = curr_visits - start_visits
            rolling_visits.append(recent_visits)
            
        rolling_visits = np.array(rolling_visits)
            
        print(curr_visits)
        print(start_visits)
        
        # add result to dataframe
        df.loc[group.index, 'recent_df_visits'] = rolling_visits
            
    return df
'''
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



