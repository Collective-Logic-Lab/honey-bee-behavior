# Running locally:
## Step One: Download the Required Programs

### Python
Python is the main programming language used for this project. If you already have Python installed, just make sure you have Python 3 installed (the modern edition, as opposed to Python 2, the legacy edition).
You can check this by running “python --version” or “python3 --version” in your command line. If you don’t have Python installed, check the link below to find the right version.
https://realpython.com/installing-python/

You could also use command line 

    For Windows:  winget install Python.Python.3 
    
    For Linux (Ubuntu / Debian / Mint): 	sudo apt update
                                          sudo apt install python3 python3-pip 
    For MacOS: brew install python3 

Check: python3 --version 


### Git
Git is needed to clone and work within the Honey-Bee-Behavior repository. If you don’t have git installed, follow this link and download the right version for your system.
https://git-scm.com/install/

For Windows, You can also type on command line “winget install --id Git.Git -e --source winget”
You can check by typing on command line “git --version ” If installed correctly, it will return the active version number (e.g., git version 2.x.x) 
*check if command lines separate for Mac/Linux, you can just google it up 

### JupyterLab
JupyterLab is an interactive development environment for viewing and editing Jupyter Notebooks (.ipynb), which is used for scientific programming. It is installed as a Python package. If you plan to use JupyterLab often, you can download it outside of a virtual environment, otherwise you can install it in a virtual environment. This will just require you to redownload JupyterLab with each virtual environment you need it in.

You can also type on command line: “pip install jupyterlab” 
*check if command lines separate for Mac/Linux, you can just google it up 
https://jupyterlab.readthedocs.io/en/stable/getting_started/installation.html




## Step 2: Git Fork and Clone the Honey-Bee-Behavior Repository
There are several methods to collaborative programming on GitHub, using Forks and Branches. The preferred method here is to fork the repository.

The Honey-Bee-Behavior repository: https://github.com/Collective-Logic-Lab/honey-bee-behavior
Press the “Fork” button

<img width="473" height="265" alt="Screenshot 2026-09-14 165750" src="https://github.com/user-attachments/assets/44326dc5-3b52-4215-b7da-0c72c7ae1aa3" />

Create the Fork.


<img width="473" height="268" alt="Screenshot 2026-09-14 165940" src="https://github.com/user-attachments/assets/dfffa91b-fdb5-4bd5-b9d8-dc6ef9969213" />

<img width="467" height="270" alt="Screenshot 2026-09-14 165951" src="https://github.com/user-attachments/assets/b263c170-a790-41b5-8819-f3cb3f1958ca" />

You’re now ready to clone this repository.

Open your terminal, and navigate to the folder you want your repository to live in.
Run:
"git clone <web url of your repository>.git"
You can also find the web url.git by pressing the “Code” button

<img width="477" height="267" alt="Screenshot 2026-09-14 170006" src="https://github.com/user-attachments/assets/8c769af5-36fc-490e-b142-53a13e8d0efc" />


After you cd into the folder honey-bee-behavior, type
"git checkout main" and "git pull origin main"

You don’t need to create another branch to start off, but if you ever need to create another branch besides main:

To create your branch and switch to it, type:
"git checkout -b <branch name>"

"git branch" should now show your branch and have a little star next to it!


## Step 3: Create a Virtual Environment with the Right Packages

A virtual environment is needed to contain the required packages in one project, preventing version conflicts with other project packages. To create a virtual environment, go into the honey-bee-behavior folder and type: 
“python3 -m venv <environment name>”

If you are not using Powershell, find the relevant commands here:
https://docs.python.org/3/library/venv.html

To activate your virtual environment, type: 
“<environment name>\Scripts\Activate.ps1”


Once your virtual environment is activated, you should see your environment name in parentheses at the start of each line. Make sure whenever you download a package or run a file in this project, you have the virtual environment activated!

To deactivate your virtual environment, you can either close the tab with the virtual environment, or type:
“Deactivate”

<img width="488" height="75" alt="Screenshot 2026-09-14 170027" src="https://github.com/user-attachments/assets/52089d54-59bd-48d6-8df1-ac19290a883f" />


The packages you should install for this project are: matplotlib, pandas, and seaborn. To install them, make sure you’re virtual environment is activated, then type:
“pip install matplotlib pandas seaborn”

<img width="480" height="64" alt="Screenshot 2026-09-14 170038" src="https://github.com/user-attachments/assets/a86a5eab-a71b-4c56-bffc-dbee2608244e" />

## Step 4: Download Relevant Files

For the Honey Bee Project, the data files are in Zenodo:
2018 data: https://zenodo.org/records/6045860
2019 data (more commonly used): https://zenodo.org/record/7298798
(Hugging Face files which have the correctly ordered videos): https://huggingface.co/buckets/collective-logic-lab/honey-bee
You shouldn’t download all of these files, only the ones you need for your given task. There are hundreds of GBs of data! 

If you’re using the “animation.ipynb”, download from the 2019 files:
“Comb-contents-images2019.zip”
“Df_day1min.zip”
“Trajectories_000-019.zip”
Once the zip files are downloaded, extract the files and move the unzipped folders to the honey-bee-behavior folder. This should get you started with the needed files.

## Step 5: Open JupyterLab
Open your Terminal and navigate to the honey-bee-behavior folder using "cd".
Activate your virtual environment if not already activated, then type:
“python3 -m jupyter lab [ipynb file name]” as shown below:
“python3 -m jupyter lab animation.ipynb”
You can also just type:
“python3 -m jupyter lab” to open the program and navigate to the file you want.

Notes for JupyterLab:
- Save frequently. Just in case. command+S or File>Save Notebook.
- Don't be afraid to restart the kernel when you are debugging or updating other files your notebook is dependent on (Kernel>Restart Kernel).


## Step 6: Submit Pull Request
After you’ve changed, added to, or created a file(s), you will want to make sure those changes are up to date with the original repository. To do so, you will first commit your changes to your own branch.

Make sure all your changes are saved and head back to your terminal.

Then you can decide what changes you'd like to see made in the original repository.
Type "git status" to see the modifications you've made. Be sure to unstage the data folders or files you added—there's just not space to fit them in the repo, so keep them local.
"git restore --staged <file>" to unstage a file
"git add <file>" to stage a file

Then, if you aren’t on your main branch, push the changes from your branch to the main branch. 
"git commit -m "little note about what changes you made""
If you are an a branch besides main:
"git push -u origin <branch name>"

Finally, submit a pull request to the original repository by pressing “Contribute”. Notify and work with Dr. Daniels and all other collaborators on this project.

<img width="493" height="281" alt="Screenshot 2026-09-14 170054" src="https://github.com/user-attachments/assets/3951f823-267f-4449-b15d-441e5b2ae77c" />

<img width="469" height="264" alt="Screenshot 2026-09-14 170104" src="https://github.com/user-attachments/assets/c0710a15-ab18-4b34-867f-444a13114459" />

You now know how to set up and work through the honey bee behavior project!


# Running on supercomputer 
When your computer does not have enough room to run the code locally (which is common when working with the 2019 data set) you must connect to the SOL supercomputer at ASU and open up and run your code there

<img width="481" height="174" alt="Screenshot 2026-09-14 174032" src="https://github.com/user-attachments/assets/15d42f34-384f-4aa2-bcf2-6936efea408d" />


Let’s start with connecting with the super computer

## Setting up VPN
First, before doing anything, you need to be on the ASU Cisco VPN

Download for your operating system

https://sslvpn-im.asu.edu/CACHE/stc/1/index.html

<img width="884" height="384" alt="Screenshot 2026-09-09 154146" src="https://github.com/user-attachments/assets/9a5eaded-0e16-480f-8f1d-37bc0e7f494c" />

After downloading, Enter in sslvpn.asu.edu/2fa as the VPN address. 

<img width="326" height="174" alt="Screenshot 2026-09-09 154422" src="https://github.com/user-attachments/assets/710fc26c-cf55-43b1-8240-8238c1ae02ee" />


The next window will request:
1. username: <your asurite>
2. password: <your asurite password>

<img width="421" height="359" alt="Screenshot 2026-09-09 154540" src="https://github.com/user-attachments/assets/d69dce66-b380-4792-9569-1b1d4130d1ff" />

You will then be prompted for your 2FA method (Duo Push, Phone Call, or Passcode).
And Bam!! You are connected to the VPN

## Requesting SOL access 
Now for connecting to the supercomputer, you first need to request permission and get approved. Ensure you have your advisor/ professor near you to make the process quicker as they will be your faculty sponsoring your account 

Access to super computer link: https://rto.asu.edu/request-access-to-the-asu-supercomputers/

On the web page itself, it has a form for you to fill out, however this is slow and soon to be outdated. Instead, submit a request through the Voyager Account Manager. 

<img width="285" height="352" alt="Screenshot 2026-09-09 155127" src="https://github.com/user-attachments/assets/043805fc-820f-480c-a413-213adeaa5fb2" />


Select your position, most likely “I am a researcher” (not student) and click on Request an HPC Account 

<img width="472" height="188" alt="Screenshot 2026-09-14 174230" src="https://github.com/user-attachments/assets/8efe9c3b-e84e-49a4-8cf2-a3f9a43be612" />


From there, on that web page it will take you through clear steps on requesting an account

<img width="226" height="400" alt="Screenshot 2026-09-09 160742" src="https://github.com/user-attachments/assets/12979eb2-8ff0-49c3-acc2-ed923c120324" />


After reading through the steps on that page, you can go to the Voyager web portal:  https://voyager.rc.asu.edu/

It will have you sign in with your Asurite 

<img width="317" height="267" alt="Screenshot 2026-09-09 160853" src="https://github.com/user-attachments/assets/0e0679e9-d61b-46e0-b474-45a8e8f57e17" />


And you will fill in the requested questions such as your intended use, research, and email of your faculty supervisor. An email will be sent to them to approve and from there you will have to wait for ASU to approve your access. It should not take too long. Make sure to have your supervisor near you to help fill out the details and sections 

Once approved, you should have a HPC account 

<img width="469" height="206" alt="image" src="https://github.com/user-attachments/assets/5870cbe6-b22a-477c-9771-dc9da8bc289d" />

## Running code 

Now, for actually running your code

You will create a Git Clone of your repository as you would normally for running locally 
Creating Git Clone: 

Assuming you are working with and trying to run the honey-bee-behavior git hub, (AKA: https://github.com/Collective-Logic-Lab/honey-bee-behavior/ )

Go to your terminal, "cd" into the folder you would like this repo to live in (for example, I created the folder Honeybeelab for all my related files to be in) , and run "git clone https://github.com/Collective-Logic-Lab/honey-bee-behavior.git" 

But really, you can type “git clone” and paste the link of whatever github you are working with and it should clone the repo

<img width="235" height="38" alt="Screenshot 2026-09-09 164816" src="https://github.com/user-attachments/assets/049f4358-eaa1-4812-8713-caa0297cd28d" />

If you click on it, all related files should be that of the Git repo

<img width="577" height="352" alt="Screenshot 2026-09-09 165059" src="https://github.com/user-attachments/assets/56448b75-254b-4694-b9e0-5fe6563300ba" />

Go to Sol Web Portal:  https://sol.asu.edu/

Login

Go to files—> Home directory (Scratch saving is not permanent)

<img width="471" height="234" alt="Screenshot 2026-09-14 174754" src="https://github.com/user-attachments/assets/76fabc49-5bb3-42b1-8e54-2cb37eea878f" />

Click on upload—>Browse Folders—> and choose your git clone FOLDER 

<img width="332" height="155" alt="Screenshot 2026-09-09 165943" src="https://github.com/user-attachments/assets/93f14505-3040-4f68-b3e6-f5510f87d8eb" />

<img width="432" height="191" alt="Screenshot 2026-09-09 170018" src="https://github.com/user-attachments/assets/465c8dfe-2cfc-4f3b-8655-601b889da58c" />

<img width="724" height="188" alt="Screenshot 2026-09-09 170309" src="https://github.com/user-attachments/assets/681e3fd5-2887-4070-aaae-fc600e48269a" />

Go to interactive apps 

<img width="467" height="228" alt="Screenshot 2026-09-14 175029" src="https://github.com/user-attachments/assets/5a1d5f59-fbf0-45d8-b1bb-839b23f3a98a" />

Select Jupyter server 
<img width="427" height="411" alt="Screenshot 2026-09-09 170803" src="https://github.com/user-attachments/assets/8da2acb2-9938-4c0f-b11b-f632631e6bdf" />


Scroll down and launch, you will have 1 hour sessions, don’t worry if you are queued then starting, should not take too long 

<img width="553" height="263" alt="Screenshot 2026-09-09 170846" src="https://github.com/user-attachments/assets/98bb5f0e-77e9-4e26-9d6d-a3690216d96e" />

<img width="840" height="393" alt="Screenshot 2026-09-09 171143" src="https://github.com/user-attachments/assets/09b5bc1c-3a24-4ee2-acba-56aab8c650db" />

<img width="795" height="422" alt="Screenshot 2026-09-09 171220" src="https://github.com/user-attachments/assets/f024f1ff-d48a-4114-8632-5f90207d08c2" />

Click on Connect to Jupyter 
It should open up to here: 

<img width="857" height="422" alt="Screenshot 2026-09-09 171825" src="https://github.com/user-attachments/assets/6b8127cb-1425-4040-99bd-f0ef8a88da44" />

Click on your Honey-bee-behavior file and run anything you like just like in a regular Jupyter application on your computer!!

<img width="863" height="415" alt="Screenshot 2026-09-09 172008" src="https://github.com/user-attachments/assets/fb34876b-17cc-4b07-93ab-9553ea8ddea6" />

