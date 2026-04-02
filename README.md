# GOON Counsil

# prerequisites

## Conda installation

https://www.anaconda.com/docs/getting-started/miniconda/install/overview

or

```shell
$ make conda-install
$ make conda-setup
```

## GitHub Cli installation

https://cli.github.com/

or

```shell
$ make gh-install
```

# init

install dependencies for the local development

```bash
# create the new Conda environment
$ make env-init-conda

# install all the dependencies
$ make env-init-poetry
```

# run the council

First, run the interactive session in the project to authenticate and confirm the folder:

```bash
$ cd /home/user/myproject

$ gh copilot

# 1. log in to GitHub
# 2. add the current folder as permanently trusted to Copilot CLI
```

Run the agents of the council (in parallel):

```bash
$ make council-critic
$ make council-innovator-1
$ make council-innovator-2
$ make council-dreamer
$ make council-clerk
```

Set the goals, metrics and details in the `/home/user/myproject/.council/problem.md` file.

Run the orchestrating council job:

```shell
$ bin/council \
    --folder "/home/user/myproject" \
    --steps 1
```
