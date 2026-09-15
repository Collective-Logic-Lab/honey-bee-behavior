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
