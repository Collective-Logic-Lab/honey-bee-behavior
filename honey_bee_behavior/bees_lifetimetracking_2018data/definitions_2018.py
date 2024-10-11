import pandas as pd
import numpy as np
from matplotlib import colors
import seaborn as sns


year = 2018
startday = pd.Timestamp(year,7,16)  # actual, for 2018:   16 July  (cameras turned on)
endday = pd.Timestamp(year,10,9)    # actual, for 2018:   was 10 September, but is now 09 Oct
alldaytimestamps = pd.date_range(start=startday,end=endday,freq='D')
numdays = len(alldaytimestamps)  # just do to 43?
numbees = 4096  #  I think 4096 is the total number.  This is the total number of barcodes, NOT the total number of bees actually tracked
numsubstrates = 10 # 10 actual substrates, and then 0 for undefined
comb_daynums = np.array([ 0,  5, 10, 15, 20, 26, 30, 35, 40, 44, 65, 75, 85]) + 16 - startday.day  # days from start day, assuming start day is in July

# get bee cohort data, and just process these for a single one
cohort_data = pd.read_csv('all_cohorts.csv')
cohort_colornames = np.unique(cohort_data['cohort'])
cohort_tagids = [np.array(cohort_data[cohort_data['cohort']==name]['beeID']) for name in cohort_colornames]
cohort_birthdates = np.array([pd.Timestamp(np.array(cohort_data['DOB'][cohort_data['cohort']==c])[0],freq='D') for c in cohort_colornames])
cohort_colonynames = np.array([cohort_data[cohort_data['cohort']==name]['colony'].iloc[0] for name in cohort_colornames])

numbeestracked = np.sum([len(l) for l in cohort_tagids])

cohortorder = np.argsort(cohort_birthdates)
# change sort order to be by birthdate
cohort_colornames = cohort_colornames[cohortorder]
cohort_tagids = [cohort_tagids[c] for c in cohortorder]
cohort_uids = [np.arange(len(cohort_tagids[0]))]
for c in range(1,len(cohort_tagids)):
    nextuid = cohort_uids[-1][-1] +1
    cohort_uids.append(np.arange(nextuid,nextuid+len(cohort_tagids[c])))
cohort_birthdates = cohort_birthdates[cohortorder]
# Hey Jacob - possible to match birthdates  to "numdays"? 
# This is how I'm doing it: ((bd.cohort_birthdates[8])-(bd.startday)).days.  Yea, thats how I'm doing it too.
cohort_colonynames = cohort_colonynames[cohortorder]
# define cohort names by alphabetical greek god names
cohort_names = ['0_queen','apollo','boreas','calypso','doris','eos','filia','glaucus','helios','iris','jeno','kotys','limnades','metis','nyx','ocean','pan']

# loop through and get the 'last data date' for each bee.
cohort_lastuse_perbee = [((numdays+1)*np.ones(len(ids))).astype(int) for ids in cohort_tagids]
for cnum in range(len(cohort_tagids)): 
    # NOTE!  cohorts need to be sorted by birthday for this to work
    next_use = [cnum + 1+np.where([b in c for c in cohort_tagids[cnum+1:]])[0]
                for b in cohort_tagids[cnum]]
    used_again = np.array([len(l)>0 for l in next_use])
    for i in range(len(cohort_tagids[cnum])):
        if len(next_use[i])>0:
            cohort_lastuse_perbee[cnum][i] = ((cohort_birthdates[next_use[i][0]]-startday).days+1)
        
numcohorts = len(cohort_names)


cohort_colors = [[0,0,0],  # queen is cohort 0
                 [0.12, 0.47, 0.71, 1.],
                 [0.68, 0.78, 0.91, 1.],
                 [1.00, 0.50, 0.05, 1.],
                 [1.00, 0.73, 0.47, 1.],
                 [0.17, 0.63, 0.17, 1.],
                 [0.60, 0.87, 0.54, 1.],
                 [0.84, 0.15, 0.16, 1.],
                 [0.58, 0.40, 0.74, 1.],
                 [0.77, 0.69, 0.83, 1.],
                 [0.55, 0.34, 0.29, 1.],
                 [0.77, 0.61, 0.58, 1.],
                 [0.89, 0.47, 0.76, 1.],
                 [0.50, 0.50, 0.50, 1.],
                 [0.78, 0.78, 0.78, 1.],
                 [0.74, 0.74, 0.13, 1.],
                 [0.09, 0.75, 0.81, 1.]]

# *** - "NA": all the things that didn't fit into any of the other colors... 

# 0 - "yellow": [0, 255, 255], 
# 1 - "darkblue":[146,  49,  46], 
# 2 - "blue":[255,   0,   0], 
# 3 - "green":[81, 166,   0], 
# 4 - "orange":[34, 101, 242], 
# 5 - "pink":[255,   0, 255], 
# 6 - "brown":[36,  76, 117], 
# 7 - "grey":[137, 137, 137], 
# 8 - "white":[255, 255, 255],               
# 9 - "black":[0, 0, 0]
# this is used for identifying colors in the images.  dont change!!
color_list = np.array([[0, 255, 255],  [146,  49,  46],  [255,   0,   0],  [81, 166,   0],  [34, 101, 242],  [255,   0, 255],  [36,  76, 117], [137, 137, 137], [255, 255, 255], [0,0,0] ] )
# this is used for displaying and plotting:  can change
color_list_display_full = np.array([[0, 255, 255],  [146,  49,  46],  [255,   0,   0],  [81, 166,   0],  [34, 101, 242],  [255,   0, 255],  [36,  76, 117], [137, 137, 137], [255, 255, 255], [255,255,255] ] )
color_list_display = np.array([[0, 255, 255],  [255,  0,  0],  [255,   0,   0],  [81, 166,   0],  [34, 101, 242],  [255,   0, 255],  [36,  76, 117], [137, 137, 137], [255, 255, 255], [255,255,255] ] )
# use seaborn colors to make better looking color map, but keep the bright yellow.  use the 'matplotlib' color set, which is a bit brighter (although it seems to default to this)
useseaborncolors = True
if useseaborncolors:
    color_list_display[1:8] = np.array(sns.color_palette("tab10"))[[0,0,2,1,6,5,7]] * 255
    color_list_display[0] = [255,255,0]
    color_list_rgb = color_list_display
else:
    color_list_rgb = np.fliplr(color_list_display)
color_names = ["yellow","darkblue",'blue','green','orange','pink','brown','grey','white','black']
color_labels = ['Honey','Capped brood','Young brood','Empty comb','Pollen stores','Dance floor','Wooden frames','Peripheral galleries','white','black']
substrate_names = color_labels
substrate_names_simple = ['Honey','Brood','Empty comb','Pollen','Dance floor','Other']


# This creates a discrete colormap for showing the comb contents
cmap_comb = colors.ListedColormap(color_list_rgb/255)
cmap_bounds=np.arange(-0.5,len(color_list_rgb)+0.5)
cmap_norm = colors.BoundaryNorm(cmap_bounds, cmap_comb.N)

### Colors for plotting.  I made Michael's yellow a bit darker.  Not used anymore - used definitions above to make colormap
# comb_color_palette = ["#CCCC00", "#2E3192", "#0000FF", "#00A651", "#F26522", "#FF00FF", "#754C24", "#898989", "#000000","#333333"]
# Colors as HEX codes:
# yellow - honey - #FFFF00
# darkblue - capped brood - #2E3192
# blue - young brood - #0000FF
# green - empty comb - #00A651
# orange - pollen stores - #F26522
# pink - dancefloor - #FF00FF
# brown - wooden frames - #754C24
# grey - peripheral galleries - #898989

#################################################################################################################################
######## Processing-related
#################################################################################################################################
# amount to shift down the left comb, so that it aligns better with the right one.
leftimage_yshift = 40  # from aligning the images, this looked reasonable.  did this to test:
    # test = comb.substrate_maps[0][1].copy()
    # test[leftimage_yshift:] = test[:-leftimage_yshift]
    # f,ax = plt.subplots(1,1)
    # f.set_size_inches(10,20)
    # plt.imshow(comb.substrate_maps[0][0],alpha=0.5)
    # plt.imshow(1-np.fliplr(test),alpha=0.5)
    # plt.suptitle(shift,fontsize=25)
    # plt.show()
    # flip the left one
    
ypixels, xpixels = (5652, 3296)  # comb.substrate_maps[0][0].shape    
    
## '6-frame representation' 
# the divs are for the one at the right.  for the 
div1_r = 1880+10
div2_r=1830*2+20
div1_l = div1_r - leftimage_yshift
div2_l = div2_r - leftimage_yshift

# Spatial histogram bins
pixels_per_bin = 160
pixels_per_cm = 80  # conversion factor from Michael
#  Michael says:  (variation between cameras wasn't that huge, from 78.3 to 80.7 px per cm)

numxbins = np.round(2*xpixels/pixels_per_bin).astype(int)
numybins = np.round(ypixels/pixels_per_bin).astype(int)
x_edges = np.linspace(0,2*xpixels,numxbins+1)
y_edges = np.linspace(0,ypixels,numybins+1)       

