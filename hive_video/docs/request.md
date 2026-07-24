# Request

Hi Peter. I want to start comparing the animations with the actual videos, I'm mainly looking at Day 4 and 47 ; 2019-06-09 and 2019-07-22. 

1.1.

 We already have the Day 4 re-sequenced video of side 0 top. If possible can you also please upload side 1 top of Day 4.

1.2.

    as well as the side0
    
1.3.

    side1 tops of Day 47? 

2. Also could you please compress the videos a bit, I am running out of storage 🙃.

## Instructions

We will perform the tasks under number 1, see how they work, and then consider number 2.

For request number 1:

- First please develop an download_raw.py module that takes a day (number) and side (0, 1) and framename (top, middle, bottom) OR a filename and downloads it to CWD or optional --target folder.

- Then, please build a slurm script that uses that module to download each of the three files to /scratch/pdressla/honey-bee/downloads/, using a job array of CPUs. Suggest considering a small memory request for the download process (but single CPUs will be fine). Note that the script will need to be able to take a file locator prefix compatible with our downloader, which is welcome to modify any aspect of the file naming for systematic convenience.

- Please review the extensive documentation for the resequence tools. A second slurm script should work, again in an array, to do the first part of resequencing processing before a manual check of the detection outputs. I will then have to actually manually check those--the boundary detection is never clean.

- Also create a slurm script that assume we have the first products of the resequence processing in place, and that I have manually verified the transitions, so that the rest of the resequencing pipeline is completed. This script should include an array, in which the first script will actually to the processing, and then a second child script will launch against its own wall clock to back up the main products of the videos to the huggingface bucket (collective-logic-lab/honey-bee/resequenced). The typical folder name format there is, for example, `reseq_start03_20190608_181426_side0_top`. I think that is a good general output naming pattern.

- We need, separately, a smoke test script, again slurm, so we can pre-check and report processing timings on the cluster. I will need to run this, report the results back, and then we can tune the wall clock planning for the main runs.

- Please update the readme: the highlight of the resequencing section should be a how-to-script.

For request number 2:

- This would be a later commit after we confirm everything is running for the first request. The task here will be obvious. We should probably accept parameters like (low, medium, high), but other than that the main question would be the slurm scripting and making sure the files get home to huggingface, say under resequenced/compressed/