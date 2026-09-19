# Honey Bee Behavior: Git, GitHub, Sol, and more cheat sheet

We work in personal forks and contribute changes to the lab repository through pull requests. These instructions cover setting up your fork and GitHub CLI (`gh`), running code on ASU Sol, and moving your work between a laptop and Sol. You can use a normal terminal or a JupyterLab terminal; the checkout is created on whichever computer runs that terminal.

**1. Terminal essentials**

The **tilde (`~`) means your home directory** on the computer where the terminal is running. `~/workspace` is a folder called `workspace` inside that home directory. Your laptop and Sol have separate home directories. 

On a mac, a `~/workspace` directory is not automatically provided. You do not have to use one, but having one for all your projects can be particularly useful. From a terminal in macos you can make one using some of the commands below.

| Command | What it does |
| --- | --- |
| `pwd` | Show your current directory. |
| `hostname` | Show which computer you are using. |
| `ls` or `ls -lh` | List files; `-lh` adds details and readable file sizes. |
| `cd ~` | Go to your home directory. |
| `cd ~/workspace` | Go directly to your workspace, if it exists. |
| `cd ..` | Go up one directory. |
| `mkdir -p ~/workspace` | Create the workspace directory if needed. |
| `cat README.md` | Print a small text file in the terminal. |

`.` means the current directory; `..` means its parent. Paths starting with `/` are absolute; paths such as `notebooks/example.ipynb` are relative to your current directory. Quote names containing spaces: `cd ~/workspace/"my project"`.

- **Use Tab completion:** type part of a directory or filename and press **Tab**. If several names match, press Tab again to see choices. This saves typing and helps avoid mistakes.
- **Reuse commands:** press **↑ / ↓** to browse command history, edit a command, and press Enter to run it.
- **Get help:** try `gh --help`, `git --help`, or `man ls`. Press **q** to leave a manual page.

For a Slurm log, replace `slurm-12345.out` with your job's actual output filename:

```bash
tail -n 30 slurm-12345.out   # Show the last 30 lines.
tail -f slurm-12345.out      # Keep watching for new output.
```

Press **Ctrl-C** to stop `tail -f`; this stops the log viewer, not the Slurm job. More generally, Ctrl-C interrupts the foreground command.

**2. Check your GitHub login and connect it to Git**

You need a GitHub account, [Git](https://git-scm.com/downloads), and [GitHub CLI](https://cli.github.com/). Check that the commands are available:

```bash
git --version
gh --version
```

Replace `YOUR_GITHUB_USERNAME` with your personal GitHub username wherever it appears. It may differ from your computer username or ASURITE ID.

Start by checking whether GitHub CLI is already signed in:

```bash
gh auth status
```

If it reports a valid login for your GitHub account, continue to `gh auth setup-git` below. If you are not signed in or your login has expired, sign in through your browser and follow the prompts:

```bash
gh auth login --hostname github.com --git-protocol https --web
gh auth status
```

Then let Git use your GitHub CLI login for HTTPS cloning, fetching, and pushing:

```bash
gh auth setup-git
```

Do this whether you just signed in or were already authenticated. Git can now use the credentials managed by `gh`. Repeat this setup on each computer where you work, including Sol. See the [`gh auth login`](https://cli.github.com/manual/gh_auth_login) and [`gh auth setup-git`](https://cli.github.com/manual/gh_auth_setup-git) instructions.

**3. Fork the repository on GitHub**

1. In your browser, sign in to the same GitHub account you used with `gh` and open [Collective-Logic-Lab/honey-bee-behavior](https://github.com/Collective-Logic-Lab/honey-bee-behavior).
2. Click **Fork** near the top right.
3. Choose your personal account as the **Owner** and keep the repository name **honey-bee-behavior**.
4. Leave **Copy the main branch only** selected; that is enough to begin contributing.
5. Click **Create fork**.

Your fork will be at `https://github.com/YOUR_GITHUB_USERNAME/honey-bee-behavior`. If you already have a fork, use it. GitHub's [forking guide](https://docs.github.com/en/pull-requests/how-tos/work-with-forks/fork-a-repo) describes these steps.

**4. Clone your fork from the command line**

A fork lives on GitHub. Cloning creates a working copy on your computer. This example puts it under `~/workspace`; you can choose another parent directory.

```bash
mkdir -p ~/workspace
cd ~/workspace
git clone https://github.com/YOUR_GITHUB_USERNAME/honey-bee-behavior.git
cd honey-bee-behavior
```

If you already cloned your fork on this computer, open a terminal in that checkout instead. Run the remaining commands from inside the checkout.

**5. Add the lab repository as `upstream`**

```bash
git remote add upstream https://github.com/Collective-Logic-Lab/honey-bee-behavior.git
git fetch upstream
git remote -v
```

The output should show these repositories, each with a fetch and push entry:

| Remote name | Repository | Purpose |
| --- | --- | --- |
| `origin` | `YOUR_GITHUB_USERNAME/honey-bee-behavior` | Your fork, where you push your work. |
| `upstream` | `Collective-Logic-Lab/honey-bee-behavior` | The lab repository, where shared issues and contributions live. |

`git fetch upstream` retrieves the lab's branch information and commits without changing your working files. If `upstream` already exists, check its URL with `git remote -v` and skip adding it when it is correct.

Set your fork as the [default destination for ordinary Git pushes](https://git-scm.com/docs/git-config#Documentation/git-config.txt-remotepushDefault) in this checkout:

```bash
git config remote.pushDefault origin
git config push.default simple
```

**6. Set up the default GitHub repository**

From inside your checkout:

```bash
gh repo set-default Collective-Logic-Lab/honey-bee-behavior
gh repo set-default --view
gh issue list
```

The default should be `Collective-Logic-Lab/honey-bee-behavior`, and the issue list should contain the lab's issues. This setting belongs to this checkout; repeat it when setting up another clone, including on Sol.

The [`gh` default repository](https://cli.github.com/manual/gh_repo_set-default) determines which repository commands such as `gh issue list` and `gh issue view` address. Git's push destination is configured separately: our setup uses the lab repository for GitHub operations and your fork for ordinary pushes.

**7. Develop on branches: choose Git or GitHub CLI**

There are two ways to start a branch. **Option A uses Git directly and is the simplest starting point.** Option B uses `gh` to name and link a branch to a lab issue, specifying your fork as the branch destination. Choose one option for each new branch.

Before either option, use the **Update `main` from the lab repository** instructions in step 9. This brings both your local `main` and your fork's `main` up to date and leaves you on `main`, ready to create a branch. Keep your own changes on issue branches.

**Option A: create and check out a branch with Git**

Replace `YOUR_BRANCH` with a short, descriptive name, such as `5-clean-up-notebook-paths`:

```bash
git switch -c YOUR_BRANCH
```

This creates a branch locally and switches to it. Make your changes and commit them. When you are ready to send those commits to your fork for the first time:

```bash
git push -u origin YOUR_BRANCH
```

This creates the matching branch on your fork and sets it as the local branch's tracking branch. After subsequent commits, `git push` sends the updates. You choose the branch name and reference the lab issue when opening your pull request; including an issue number in the branch name alone does not create an issue link.

**Option B: create an issue-linked branch with `gh` (optional)**

This option lets GitHub generate the branch name from an issue, creates the branch in your fork immediately, and checks it out locally. The issue link carries through when you open a pull request, helping keep the issue, branch, and PR together. You still commit and push your code changes and open the PR. See [GitHub's issue-branch workflow](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-a-branch-for-an-issue).

The built-in `gh issue develop` command has no separate default for the branch repository. Without `--branch-repo`, it creates branches in the issue's repository. After setting the lab as the default in step 6, use the explicit command we used in the seminar:

```bash
gh issue view ISSUE_NUMBER
gh issue develop ISSUE_NUMBER -c --branch-repo YOUR_GITHUB_USERNAME/honey-bee-behavior
git status --short --branch
```

`-c` means check out the new branch. Replace the issue number and username; record the generated branch name for later pushes and the PR. The Git seminar scenario after step 9 walks through the complete process.

**Optional shortcut for repeated use**

To avoid typing `--branch-repo` each time, install this [`gh` alias](https://cli.github.com/manual/gh_alias_set) once on each computer where you want the shortcut:

```bash
gh alias set develop --shell '
branch_repo=$(git remote get-url origin) || exit
exec gh issue develop --branch-repo "$branch_repo" "$@"
'
```

The alias uses the upstream GitHub default from step 6 for the issue and reads the current checkout's `origin` for the new branch. No username needs to be hardcoded in it. Confirm `gh repo set-default --view` names the lab repository and `git remote -v` shows your fork as `origin`. If `gh alias list` already shows this definition, the alias is ready to use.

Replace `ISSUE_NUMBER` with the number of the lab issue, read it, and create its branch:

```bash
gh issue view ISSUE_NUMBER
gh develop ISSUE_NUMBER --checkout
git status --short --branch
```

The shortcut supplies `--branch-repo` to [`gh issue develop`](https://cli.github.com/manual/gh_issue_develop) and passes through your other arguments. Add `--name YOUR_BRANCH_NAME` if you want to choose the name yourself. After making and committing changes, use `git push` to update the branch in your fork.

Aliases are personal GitHub CLI settings and are not transferred by cloning a repository. Set this up separately on your laptop and Sol if using this option on both. The original `gh issue develop` command keeps its standard behavior; use `gh develop` for this configured workflow.

**8. Develop, commit, and contribute updates**

An issue branch holds the work for a particular task. Whether you created it with Git or `gh` in step 7, the cycle is the same: **edit → check → stage → commit → push → review**. Keep related updates on that branch so they stay together in one pull request.

**Work on the intended branch**

Read the lab issue and coordinate the scope with anyone else working on it. Check your current work before switching to an existing branch:

```bash
git status
git switch YOUR_BRANCH
git status --short --branch
gh issue view ISSUE_NUMBER
```

Preserve unfinished work before switching. Here `git switch YOUR_BRANCH` returns to a branch you already created; `git switch -c` is for creating a new one. You can also read the issue on GitHub. For work moving between your laptop and Sol, follow the update sequence in 10c.

**Edit, save, and check your changes**

Edit in your usual editor or Jupyter, save the files, and run an appropriate small example or check. For a notebook, review changed cells and outputs as well as the code. Then inspect what changed:

```bash
git status
git diff
```

`git status` lists changed and new files. `git diff` shows unstaged changes to tracked files; read new files directly until they are staged. Press **q** if a diff opens in a pager. Keep generated data and unrelated edits out of the contribution.

**Stage and commit one coherent update**

Replace `PATH_TO_CHANGED_FILE` with the file you intend to include, repeating `git add` for other intended files:

```bash
git add PATH_TO_CHANGED_FILE
git diff --staged
```

Staging selects what the next commit will contain. Check the staged diff before committing; if you edit a file again, stage it again to include those later edits. To unstage a file while keeping its edits, use `git restore --staged PATH_TO_CHANGED_FILE`.

If Git has not been configured with your author identity, set it for this checkout. Use your name and an email associated with your GitHub account, or your GitHub-provided `noreply` address:

```bash
git config user.name "Your Name"
git config user.email "YOUR_COMMIT_EMAIL"
```

This is separate from `gh` authentication. See GitHub's [commit email guidance](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address).

Create a commit with a short description of the change:

```bash
git commit -m "Clarify notebook data paths"
git status
```

A commit records the staged update locally. Saving a file, committing it, and pushing the commit are separate steps.

**Push the issue branch to your fork**

For the first push, or to explicitly establish tracking:

```bash
git push -u origin YOUR_BRANCH
```

For later commits on that branch, use `git push`. This sends the commits to your fork. If a push is rejected because the remote has newer work, coordinate and bring your checkout up to date before trying again.

**Open a pull request and continue the review**

On GitHub, open a PR from your fork's branch into `Collective-Logic-Lab/honey-bee-behavior`, with `main` as the base. Alternatively, use [`gh pr create`](https://cli.github.com/manual/gh_pr_create), replacing the username and branch placeholders:

```bash
gh pr create --draft \
  --repo Collective-Logic-Lab/honey-bee-behavior \
  --base main \
  --head YOUR_GITHUB_USERNAME:YOUR_BRANCH
```

Follow the prompts for the title and description. Explain what changed, why, what you checked, and what remains uncertain. Use a draft while work is in progress and mark it ready when it is ready for review.

For a contribution that addresses part of a larger issue, write `Refs #ISSUE_NUMBER` in the lab PR description and explain what remains. Use `Closes #ISSUE_NUMBER` when the PR completes the issue. A PR from a `gh issue develop` branch (including the `gh develop` shortcut) can already have a closing issue link: for partial work, have a maintainer check and remove that link before merging. See GitHub's [issue-linking behavior](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue).

To address feedback, make further edits on the same branch, check them, commit, and push. The existing PR updates automatically; you do not need a new branch or PR for each revision. Follow the lab's [contribution guide](https://github.com/Collective-Logic-Lab/honey-bee-behavior/blob/main/CONTRIBUTING.md); repository administrators handle merges.

**9. Fetch and pull updates**

Your checkout, your fork (`origin`), and the lab repository (`upstream`) are separate copies. New commits do not move between them automatically.

- **[`git fetch`](https://git-scm.com/docs/git-fetch)** downloads commits and updates your local view of a remote's branches without changing your working files or current branch.
- **[`git pull`](https://git-scm.com/docs/git-pull)** fetches and then integrates a remote branch into your **current branch**. Use `--ff-only` to allow a straightforward update and stop if the histories have diverged.

To refresh your view of either remote:

```bash
git fetch origin     # Your fork.
git fetch upstream   # The lab repository.
```

For example, `upstream/main` now refers to the lab's `main` as of that fetch; your local `main` has not moved yet. Pull already includes a fetch, so a separate fetch is optional before the recipes below.

**Update `main` from the lab repository**

Do this before starting a new issue branch or after contributions are merged. Save your files, run `git status`, and commit any intended edits on their issue branch first. Continue only with a clean working tree. Save and close open notebooks before switching branches or pulling.

```bash
git status
git switch main
git pull --ff-only upstream main
git push origin main
```

The pull brings the lab's changes into your local `main`; the push sends that updated `main` to your fork. Run each command only if the preceding one succeeds. You can now create a new issue branch using step 7.

**Update an existing issue branch from your fork**

Use this when new commits have been pushed to the same branch from another computer, such as your laptop or Sol. With a clean working tree:

```bash
git status
git switch YOUR_BRANCH
git pull --ff-only origin YOUR_BRANCH
```

This assumes the branch already exists locally and on your fork; see 10c for its first checkout on Sol. Reopen notebooks and restart their kernels after updating so they use the new code.

Updating `main` does **not** update an existing issue branch. Bringing newer lab changes into ongoing work is a separate merge or rebase step; the seminar scenario below shows the merge approach. If a pull or push is rejected, stop and inspect the situation with a collaborator before continuing.

<details>
<summary><strong>From the seminar: take an issue from your fork through review and back to main</strong></summary>

This expands the seminar's fork-and-PR workflow into a complete sequence. Start with your own fork on GitHub and the login from steps 2–3. Replace `YOUR_GITHUB_USERNAME`, `ISSUE_NUMBER`, `YOUR_BRANCH`, and `PR_NUMBER` as you go; issue and PR numbers are different. Run commands one step at a time and stop if a command fails. Before switching branches or merging, save and close notebooks and preserve your edits in commits on the appropriate branch.

**A. Clone your fork and connect it to the lab repository**

For a new checkout:

```bash
mkdir -p ~/workspace
cd ~/workspace
git clone https://github.com/YOUR_GITHUB_USERNAME/honey-bee-behavior.git
cd honey-bee-behavior
git remote add upstream https://github.com/Collective-Logic-Lab/honey-bee-behavior.git
```

If you already cloned the repository, enter that checkout instead. Check `git remote -v`; add `upstream` only if it is missing. If it points elsewhere, correct it with `git remote set-url upstream https://github.com/Collective-Logic-Lab/honey-bee-behavior.git`.

```bash
git remote -v
git config remote.pushDefault origin
git config push.default simple
gh repo set-default Collective-Logic-Lab/honey-bee-behavior
gh repo set-default --view
gh issue list
```

Confirm that `origin` is your fork, `upstream` is the lab repository, and the issues belong to the lab. These are separate settings: Git knows where to fetch and push, while `gh` knows where to look for issues and PRs. If your commit identity is not configured, set it for this checkout:

```bash
git config user.name "Your Name"
git config user.email "YOUR_COMMIT_EMAIL"
```

Use an email associated with your GitHub account, including its `noreply` address if preferred.

**B. Update both copies of main, then create the issue branch**

Continue with a clean working tree:

```bash
git status
git fetch upstream
git switch main
git merge --ff-only upstream/main
git push origin main
gh issue view ISSUE_NUMBER
gh issue develop ISSUE_NUMBER -c --branch-repo YOUR_GITHUB_USERNAME/honey-bee-behavior
git branch --show-current
git status --short --branch
```

The push updates your fork's `main` on GitHub, so the new branch can start from the latest lab code. The default `gh` repository supplies the issue, `--branch-repo` selects your fork, and `-c` checks out the new branch. No alias is needed. Record the generated branch name and substitute it for `YOUR_BRANCH` below. If the branch already exists, use `git switch YOUR_BRANCH` rather than creating it again. See the [`gh issue develop` reference](https://cli.github.com/manual/gh_issue_develop).

**C. Develop and commit on that branch**

Edit and save your files, then run an appropriate check or small example. Stage only the files you intend to contribute, repeating `git add` as needed:

```bash
git status --short --branch
git diff
git add PATH_TO_CHANGED_FILE
git diff --staged
git commit -m "Describe the change"
git status
```

**D. Check upstream again before opening the PR**

The lab may have merged other work while you were editing. With your changes committed and your working tree clean, bring that work into the issue branch:

```bash
git switch YOUR_BRANCH
git fetch upstream
git log --oneline HEAD..upstream/main
git merge --no-edit upstream/main
```

The log shows upstream commits your branch does not yet contain. This merge can create a merge commit when both branches have changed; it preserves your existing commits. If Git reports conflicts, stop before pushing. Resolve the marked files with a collaborator, stage the resolved files, and finish with `git commit`. To abandon that merge attempt and return to your pre-merge work, use `git merge --abort`.

After a successful merge, rerun the relevant checks and inspect the contribution relative to the lab:

```bash
git status
git diff --stat upstream/main...HEAD
git diff upstream/main...HEAD
git push -u origin YOUR_BRANCH
gh pr create --repo Collective-Logic-Lab/honey-bee-behavior \
  --base main --head YOUR_GITHUB_USERNAME:YOUR_BRANCH
```

Follow the prompts for the PR title and description. Explain the change and checks, and reference the lab issue as described in step 8. An issue-linked branch can close its issue when merged, so check that association if this PR only completes part of the issue. Record the PR number from the resulting URL. The repository administrators handle the merge.

**E. If a reviewer requests changes, continue on the same branch**

A request for changes is another round of development. Open the review, including comments attached to particular lines:

```bash
gh pr view PR_NUMBER --repo Collective-Logic-Lab/honey-bee-behavior --web
git status
git switch YOUR_BRANCH
git pull --ff-only origin YOUR_BRANCH
```

Continue only with a clean working tree and a successful pull. Make the requested edits, save, and run the relevant checks. Then:

```bash
git diff
git add PATH_TO_CHANGED_FILE
git diff --staged
git commit -m "Address review feedback"
```

Repeat step D's upstream fetch and merge, rerun checks if the merge changes your code, and push:

```bash
git push origin YOUR_BRANCH
```

The existing PR receives these commits automatically. Reply to the reviewer on GitHub with what changed and request another look; a new PR is unnecessary for an open review. If the PR was actually **closed without merging**, pushing does not reopen it. Discuss whether to reopen it or take a different approach before continuing.

**F. After the PR is merged, sync main and retire the completed branch**

Check the specific PR first:

```bash
gh pr view PR_NUMBER --repo Collective-Logic-Lab/honey-bee-behavior \
  --json state,headRefName,headRefOid
git rev-parse YOUR_BRANCH
git status
```

Continue only when the PR state is `MERGED`, its branch name is the one you intend to retire, its `headRefOid` matches the local branch hash, and your working tree is clean. If the hashes differ, keep the branch and inspect it for later or unpushed work.

```bash
git switch main
git pull --ff-only upstream main
git push origin main
git branch -d YOUR_BRANCH
```

You are now back on local `main`, and both it and your fork's remote `main` contain the merged lab changes. If the pull or push fails, stop before deleting anything. Delete the completed **branch**, not the GitHub issue, which remains a useful record of the work.

After a squash merge, Git may refuse `git branch -d` because the merged commit has a different identity. Only after the checks above confirm that the exact branch contents were merged and no later work remains, remove that local branch with:

```bash
git branch -D YOUR_BRANCH
```

Do not use `-D` as an automatic response to a deletion error. Conversely, a successful `-d` alone does not prove a PR was merged: Git may be comparing with the branch in your fork. See [Git's branch deletion rules](https://git-scm.com/docs/git-branch).

Optionally remove the completed branch from your fork too. First fetch and check that its remote hash still matches the merged PR's `headRefOid`:

```bash
git fetch origin --prune
git rev-parse origin/YOUR_BRANCH
```

If it matches and nobody is continuing work there, replace `MERGED_HEAD_HASH` below with that full verified `headRefOid`:

```bash
git push --force-with-lease=refs/heads/YOUR_BRANCH:MERGED_HEAD_HASH \
  origin --delete YOUR_BRANCH
git fetch origin --prune
```

The lease makes deletion conditional on the remote branch still having that exact hash. If it is rejected, stop and inspect; do not retry without the lease. Skip remote deletion if GitHub already removed the branch. Start the next task from updated `main` with a new issue branch.

</details>

**10. Work on ASU Sol**

These instructions follow the repository's [Sol environment guide](https://github.com/Collective-Logic-Lab/honey-bee-behavior/blob/main/envs/README.md). You need a Sol account and access to the `grp_bdaniel6` group. The shared Mamba environment supplies Python, the project dependencies, and `gh`; your own Sol account holds your GitHub login and repository checkout.

**10a. Use a Sol terminal: activate, authenticate, clone, and run**

Connect through the [Sol web portal](https://sol.asu.edu), using **System → Shell Access**, or run this from your laptop's terminal, replacing `YOUR_ASURITE` with your ASU login:

```bash
ssh YOUR_ASURITE@sol.asu.edu
```

Follow ASU's [connection instructions](https://docs.rc.asu.edu/connecting/) for VPN and login requirements. The following commands run in the **Sol terminal**.

Request a compute session, then activate the shared environment. Wait for the allocation to start before continuing:

```bash
interactive
module load mamba/latest
source activate /data/grp_bdaniel6/envs/honey-bee-behavior-v1
gh --version
```

This is the repository's basic allocation for quick checks. Choose suitable CPU, memory, and time requests for larger work using ASU's [resource guide](https://docs.rc.asu.edu/requesting-resources/). Run analyses in a compute allocation. If you are already in one, including a Sol Jupyter session, skip `interactive`.

Check your GitHub login on Sol:

```bash
gh auth status
```

If needed, sign in:

```bash
gh auth login --hostname github.com --git-protocol https --web
```

Open the URL printed by `gh` in your laptop's browser and enter the one-time code it displays. The login authorizes `gh` running under your Sol account. Then connect Git to that login, whether you just signed in or were already authenticated:

```bash
gh auth setup-git
```

Clone your personal fork into your Sol workspace and configure this checkout:

```bash
mkdir -p ~/workspace
cd ~/workspace
git clone https://github.com/YOUR_GITHUB_USERNAME/honey-bee-behavior.git
cd honey-bee-behavior
git remote add upstream https://github.com/Collective-Logic-Lab/honey-bee-behavior.git
git config remote.pushDefault origin
git config push.default simple
gh repo set-default Collective-Logic-Lab/honey-bee-behavior
git remote -v
```

If the checkout already exists, enter it and check its remotes instead of cloning or adding `upstream` again. As on your laptop, `origin` should be your fork and `upstream` should be the lab repository.

Usually, check out the branch you already pushed from your laptop, as shown in the Sol seminar scenario below and in 10c. To start a new branch on Sol, choose either option in step 7; `gh issue develop ISSUE_NUMBER -c --branch-repo YOUR_GITHUB_USERNAME/honey-bee-behavior` needs no alias.

From the repository root, check the environment:

```bash
python envs/sol/confirm_env_sol.py
```

This checks Python, imports, package dependencies, small HDF5 and plotting operations, and command-line tools. It does not establish that every analysis works. If `gh` is missing after activation, ask a maintainer to check the shared installation; older builds may predate its addition.

Try a CLI command using the small video already included in the repository:

```bash
hive-video --help
mkdir -p data/temp/sol-demo
hive-video fragment \
  --video data/examples/resequenced_example.mp4 \
  --start-seconds 0 \
  --duration-seconds 1 \
  --out data/temp/sol-demo/one_second.mp4
```

This writes a one-second video and its JSON metadata on Sol. Use a new output filename when repeating the example; existing outputs are protected against overwriting. Other analyses may need separately configured data paths. Large datasets and outputs should use the appropriate project or scratch storage, following the [repository guide](https://github.com/Collective-Logic-Lab/honey-bee-behavior/blob/main/envs/README.md).

For each new Sol terminal or job, load the Mamba module and activate the environment again. Your GitHub login normally persists under your Sol account. When finished with a terminal compute session, use `exit` to release that allocation. If setting up Jupyter next, register its kernel below before exiting.

<details>
<summary><strong>From the seminar: first-time Git and GitHub setup on Sol</strong></summary>

Use this sequence if you have a Sol account but have not configured Git or cloned the repository there. Your personal GitHub fork should already exist; use the same fork as on your laptop. Sol has its own checkout, authentication, and Git settings.

**A. Activate the environment before setting up GitHub access**

Open Sol's **System → Shell Access** in the web portal, or connect by SSH as described in 10a. In that Sol terminal, request a compute allocation:

```bash
interactive
```

Wait until the allocation starts. If you are using a terminal inside an existing Sol Jupyter allocation, skip `interactive`. Then:

```bash
module load mamba/latest
source activate /data/grp_bdaniel6/envs/honey-bee-behavior-v1
gh --version
gh auth status --hostname github.com
```

Activating the shared environment makes its `gh` command available. If the status check says you are not logged in, sign in:

```bash
gh auth login --hostname github.com --git-protocol https --web
```

Open the printed URL in your laptop's browser and enter the code printed in the Sol terminal. After login, or if you were already authenticated, connect Git to those credentials:

```bash
gh auth setup-git --hostname github.com
gh auth status --hostname github.com
```

This configures Git on Sol to use your GitHub CLI login for HTTPS operations, including cloning and pushing. It does not copy your laptop's Git configuration or set the author name and email for commits. See [`gh auth setup-git`](https://cli.github.com/manual/gh_auth_setup-git).

**B. Clone once, then configure the checkout**

```bash
mkdir -p ~/workspace
cd ~/workspace
git clone https://github.com/YOUR_GITHUB_USERNAME/honey-bee-behavior.git
cd honey-bee-behavior

git config user.name "Your Name"
git config user.email "YOUR_COMMIT_EMAIL"
git remote add upstream https://github.com/Collective-Logic-Lab/honey-bee-behavior.git
git config remote.pushDefault origin
git config push.default simple
gh repo set-default Collective-Logic-Lab/honey-bee-behavior

git remote -v
gh repo set-default --view
gh issue list
git fetch upstream
git switch main
git merge --ff-only upstream/main
git push origin main
python envs/sol/confirm_env_sol.py
```

Replace the username, name, and email placeholders with your own details; the email should be associated with GitHub or be your GitHub `noreply` address. This sets commit authorship for this checkout. Run each command only after the preceding one succeeds. The remotes should identify your fork as `origin` and the lab as `upstream`; `gh` should show the lab's issues. The final command checks the software environment.

**C. Run the work you pushed from your laptop**

We generally use Sol to execute code developed on laptops, so most commits will come from your laptop. Commit and push your issue branch there first. For its first checkout on Sol:

```bash
git fetch origin
git switch --track origin/YOUR_BRANCH
git status --short --branch
git log -1 --oneline
```

If the branch already exists locally, save and close notebooks and confirm a clean working tree, then use:

```bash
git status
git switch YOUR_BRANCH
git pull --ff-only origin YOUR_BRANCH
git log -1 --oneline
```

You can now run the CLI example in 10a or open notebooks using the shared Jupyter kernel in 10b. Reopen notebooks and restart their kernels after pulling code updates. A branch switch selects code; environment activation and kernel selection select the Python environment.

**D. Save an intentional notebook improvement made on Sol**

An exception to laptop-first development is a notebook you edit while running it on Sol. Save it, review its code, outputs, and metadata, and commit only the changes worth sharing. On the same issue branch:

```bash
git status --short --branch
git diff -- notebooks/YOUR_NOTEBOOK.ipynb
git add notebooks/YOUR_NOTEBOOK.ipynb
git diff --staged
git commit -m "Describe the notebook improvement"
git push -u origin YOUR_BRANCH
```

Running cells alone may change outputs and execution counts; those changes do not all need to become a contribution. If a push is rejected because the branch has advanced elsewhere, preserve your commit and resolve the divergence with a collaborator before continuing.

Before making further edits on your **laptop**, save and preserve any local work, then with a clean working tree:

```bash
cd ~/workspace/honey-bee-behavior
git status
git switch YOUR_BRANCH
git pull --ff-only origin YOUR_BRANCH
git log -1 --oneline
```

The Sol commit is now available locally and, if the branch already has an open PR, in that same PR. Follow the Git seminar scenario above for upstream checks, review, and cleanup. Saving a notebook on Sol is not enough to transfer it: commit, push, then pull on the other computer.

On later visits, load the Mamba module and activate the environment again; the login and checkout settings normally persist. Use `exit` to release a shell allocation when finished, or stop a Jupyter allocation through **My Interactive Sessions** in the portal.

</details>

**10b. Use Jupyter on Sol with the shared environment**

After activating the shared environment, register it as a kernel for your Sol account. Do this once for each environment version:

```bash
python -m ipykernel install --user \
  --name honey-bee-behavior-v1 \
  --display-name "Honey Bee Behavior (v1)"
```

This registers the existing environment with Jupyter, following ASU's [instructions for environments under `/data`](https://docs.rc.asu.edu/jupyter-kernels/#creating-kernels-from-a-data-directory).

1. Open the [Sol web portal](https://sol.asu.edu) and choose **Interactive Apps → Jupyter**.
2. Request resources appropriate for your notebook, launch the session, and connect when it is ready.
3. In Jupyter, navigate to your Sol checkout, such as `workspace/honey-bee-behavior/notebooks`, and open a notebook.
4. Select **Honey Bee Behavior (v1)** as its kernel.

Your laptop displays the browser interface; the notebook files and Python process are on Sol. Check the selected Python and current directory in a notebook cell:

```python
import sys
from pathlib import Path

print("Python:", sys.executable)
print("Working directory:", Path.cwd())
```

The Python path should be inside `/data/grp_bdaniel6/envs/honey-bee-behavior-v1`. Start with the setup and fragment cells in `notebooks/hive-video-examples.ipynb`. Skip its package-installation cell when using the shared environment; the dependencies are already installed. Run the cells needed for your example in order.

A terminal opened inside this Sol Jupyter session also runs on Sol, within its allocation. To use the environment's commands there, run:

```bash
module load mamba/latest
source activate /data/grp_bdaniel6/envs/honey-bee-behavior-v1
cd ~/workspace/honey-bee-behavior
```

Selecting a notebook kernel and activating a terminal environment are separate actions. You can use that terminal for `git`, `gh`, and CLI commands alongside your notebook. If you started with Jupyter before cloning, use this terminal to follow the authentication and cloning steps in 10a, skipping `interactive`.

When finished, save your notebooks and stop the session through the portal's **My Interactive Sessions** page. Closing a browser tab alone does not end the compute session. See ASU's [portal guide](https://docs.rc.asu.edu/web-portal/).

**10c. Develop on your laptop and run your fork's branch on Sol**

Your fork lets you try work on Sol before it is merged into the lab repository. The route is **laptop checkout → your fork on GitHub → Sol checkout**. Replace `YOUR_BRANCH` with your actual branch name, and `PATH_TO_CHANGED_FILE` with a file you intend to commit.

On your **laptop**, save your edits, including notebook changes, and check which branch you are on:

```bash
git status
git branch --show-current
git diff
```

On the intended branch, stage and commit the changes you want to try, then push that branch to your fork:

```bash
git add PATH_TO_CHANGED_FILE
git diff --staged
git commit -m "Describe the change being tested on Sol"
git push -u origin YOUR_BRANCH
```

Repeat `git add` for other intended files as needed. If the changes are already committed, only the push is needed. Uncommitted changes stay on your laptop.

On **Sol**, activate the shared environment as in 10a and enter your fork's checkout. Before switching or updating a branch, save and close open notebooks and run `git status`. Continue with a clean working tree; preserve any Sol edits in their own commits first.

For the **first checkout of this branch on Sol**:

```bash
cd ~/workspace/honey-bee-behavior
git status
git fetch origin
git switch --track origin/YOUR_BRANCH
```

This creates a local branch that tracks the branch in your fork. If the local branch already exists, use the update commands below instead.

For **later updates**, commit and push new changes from your laptop, then run on Sol:

```bash
git status
git switch YOUR_BRANCH
git pull --ff-only origin YOUR_BRANCH
git log -1 --oneline
```

The fast-forward-only pull stops if the laptop and Sol histories have diverged. If it fails, inspect the changes with a collaborator before continuing. Compare `git log -1 --oneline` on both machines to confirm they are at the same commit.

Now run your script or CLI example from the Sol checkout, or reopen the notebook in Sol Jupyter. Select the shared kernel, restart it to clear previously imported code, and rerun the required cells.

Git transfers committed repository files. Your environment, kernel registration, ignored data, and generated outputs are separate. The shared environment supplies installed dependencies: switching a branch in `honey-bee-behavior` does not change an installed package such as `hive-video`, which comes from the separate `honeybee-hive-video` project. For different dependencies or editable package development, use a personal development environment as described in the [environment guide](https://github.com/Collective-Logic-Lab/honey-bee-behavior/blob/main/envs/README.md).

If you also make and commit changes on Sol, push that branch to your fork before returning to laptop work. Update the laptop checkout with the same `git pull --ff-only origin YOUR_BRANCH` pattern before continuing.

**11. Work with the Hugging Face bucket using `hf`**

The lab's [Honey Bee bucket](https://huggingface.co/buckets/collective-logic-lab/honey-bee) holds data and analysis artifacts separately from the GitHub code repository. Its command-line address is `hf://buckets/collective-logic-lab/honey-bee`. Run these commands on the computer where you want the files: your laptop or a Sol terminal, including one opened through Jupyter.

**Check the CLI and log in**

On Sol, activate the shared environment as in 10a first; the current environment recipe includes `hf`. Check that your installed version has bucket commands and check your login:

```bash
hf version
hf buckets --help
hf auth whoami
```

If `hf` is missing on your laptop, follow the [CLI installation instructions](https://huggingface.co/docs/huggingface_hub/guides/cli#getting-started). If `hf` or its bucket commands are missing in the shared Sol environment, ask a maintainer to update it.

If you need to log in:

```bash
hf auth login
hf auth whoami
```

Follow the browser login if your version offers it. Versions that request a token need one from your [Hugging Face token settings](https://huggingface.co/settings/tokens); paste it at the hidden prompt. Keep tokens out of notebooks and shell commands. This uses your own Hugging Face account and is separate from `gh` authentication; repeat it on each computer. Bucket transfers do not need Git credential setup. See the [login guide](https://huggingface.co/docs/huggingface_hub/guides/cli#hf-auth-login).

**Browse before downloading**

```bash
hf buckets list collective-logic-lab/honey-bee --human-readable
hf buckets list collective-logic-lab/honey-bee/experiment_example_5s --human-readable
```

The second command looks inside an existing example folder. Check file sizes and choose the files you need; raw videos can be large.

**Download a small example**

From your `honey-bee-behavior` checkout, download the example's metadata:

```bash
mkdir -p data/temp/hf-demo
hf buckets cp \
  hf://buckets/collective-logic-lab/honey-bee/experiment_example_5s/metadata.json \
  data/temp/hf-demo/metadata.json
cat data/temp/hf-demo/metadata.json
```

`cp` takes the **source first, destination second**. Use a new local filename if you need to preserve an earlier download. For larger data on Sol, choose an appropriate project or scratch directory as described in the environment guide.

To download the whole example folder, first preview the transfer:

```bash
hf buckets sync \
  hf://buckets/collective-logic-lab/honey-bee/experiment_example_5s \
  data/temp/hf-demo --dry-run
```

Check the plan, then repeat the command without `--dry-run` to transfer the files. `sync` adds or updates destination files; it can overwrite existing versions. These examples omit `--delete`, which would also remove destination files absent from the source. See the [bucket transfer guide](https://huggingface.co/docs/huggingface_hub/guides/buckets).

**Upload a result when you have write access**

Your account and token need permission to write to the lab bucket. Agree on a destination path with the lab, then replace both placeholders below with your local result file and a new bucket path, including its filename:

```bash
hf buckets cp PATH_TO_LOCAL_RESULT \
  hf://buckets/collective-logic-lab/honey-bee/PATH_TO_NEW_BUCKET_FILE
```

Bucket changes take effect directly and do not have Git commits, branches, or pull requests. Use distinct output names to preserve earlier results, and record the bucket path, input data, and code commit in your analysis notes. Git pushes do not transfer these data files. Hugging Face documents [bucket access controls](https://huggingface.co/docs/hub/storage-buckets-security#access-control).

---

This document was produced by Peter Dresslar in conjunction with GPT-6 Astra(Ultra).