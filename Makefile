SHELL := /bin/bash
ROOT  := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
DATE  := $(shell date '+%Y%m%d-%H%M%S')

CONDA_ENV_NAME      = council

RSYNC               = rsync --archive --verbose --compress --rsh='ssh -o ClearAllForwardings=yes'

REMOTE_HOST        ?= pp-council
REMOTE_PATH        ?= projects/council

CONDA_VERSION      = py312_25.9.1-3
GH_VERSION         = 2.88.1
COPILOT_VERSION    = 1.0.14

# -----------------------------------------------------------------------------
# notebook
# -----------------------------------------------------------------------------

.DEFAULT_GOAL = run

# -----------------------------------------------------------------------------
# conda installation
# -----------------------------------------------------------------------------

.PHONY: conda-install
conda-install:
	@wget -qc -O '${HOME}/miniconda.sh' 'https://repo.anaconda.com/miniconda/Miniconda3-$(CONDA_VERSION)-Linux-x86_64.sh'
	@mkdir -p "${HOME}/opt"
	@bash '${HOME}/miniconda.sh' -b -f -p "${HOME}/opt/miniconda"
	@mkdir -p "${HOME}/.local/bin"
	@ln -sfT "${HOME}/opt/miniconda/bin/conda" "${HOME}/.local/bin/conda"
	@rm -vf '${HOME}/miniconda.sh'

.PHONY: conda-setup
conda-setup:
	@conda config --system --set solver libmamba
	@conda tos accept --override-channels --channel 'https://repo.anaconda.com/pkgs/main'
	@conda tos accept --override-channels --channel 'https://repo.anaconda.com/pkgs/r'
	@conda config --system --remove channels defaults
	@conda config --system --add channels conda-forge
	@conda config --system --add channels nvidia
	@conda config --show-sources
	@conda config --show channels

# -----------------------------------------------------------------------------
# github cli installation
# -----------------------------------------------------------------------------

.PHONY: gh-install
gh-install:
	@mkdir -p "${HOME}/opt/gh"
	@wget -qc -O - "https://github.com/cli/cli/releases/download/v$(GH_VERSION)/gh_$(GH_VERSION)_linux_amd64.tar.gz" | tar xvz -C "${HOME}/opt/gh"
	@chmod ugo=+x "${HOME}/opt/gh/gh_$(GH_VERSION)_linux_amd64/bin/gh"
	@mkdir -p "${HOME}/.local/bin"
	@ln -sfT "${HOME}/opt/gh/gh_$(GH_VERSION)_linux_amd64/bin/gh" "${HOME}/.local/bin/gh"

# -----------------------------------------------------------------------------
# copilot cli installation
# -----------------------------------------------------------------------------

.PHONY: copilot-install
copilot-install:
	@mkdir -p "${HOME}/opt/copilot-${COPILOT_VERSION}"
	@wget -qc -O - "https://github.com/github/copilot-cli/releases/download/v${COPILOT_VERSION}/copilot-linux-x64.tar.gz" | tar xvz -C "${HOME}/opt/copilot-${COPILOT_VERSION}"
	@chmod ugo=+x "${HOME}/opt/copilot-${COPILOT_VERSION}/copilot"
	@ln -sfT "${HOME}/opt/copilot-${COPILOT_VERSION}/copilot" "${HOME}/.local/bin/copilot"

# -----------------------------------------------------------------------------
# conda environment
# -----------------------------------------------------------------------------

.PHONY: env-init-conda
env-init-conda:
	@conda create --yes --copy --name "$(CONDA_ENV_NAME)" \
		conda-forge::python=3.12.12 \
		conda-forge::poetry=2.2.1

.PHONY: env-init-poetry
env-init-poetry:
	@conda run --no-capture-output --live-stream --name "$(CONDA_ENV_NAME)" \
		poetry install --no-root --no-directory

.PHONY: env-update
env-update:
	@conda run --no-capture-output --live-stream --name "$(CONDA_ENV_NAME)" \
		poetry update

.PHONY: env-list
env-list:
	@conda run --no-capture-output --live-stream --name "$(CONDA_ENV_NAME)" \
		poetry show

.PHONY: env-remove
env-remove:
	@conda env remove --yes --name "$(CONDA_ENV_NAME)"

.PHONY: env-shell
env-shell:
	@conda run --no-capture-output --live-stream --name "$(CONDA_ENV_NAME)" --cwd "$(ROOT)/src"\
		bash

.PHONY: env-info
env-info:
	@conda run --no-capture-output --live-stream --name "$(CONDA_ENV_NAME)" \
		conda info

# -----------------------------------------------------------------------------
# test
# -----------------------------------------------------------------------------

.PHONY: tests
tests:
	@bin/run pytest -v -p no:cacheprovider "$(ROOT)/tst/"

# -----------------------------------------------------------------------------
# council
# -----------------------------------------------------------------------------

.PHONY: council-innovator-1
council-innovator-1:
	@gh copilot \
		--acp \
		--port 10001 \
		--yolo \
		--enable-all-github-mcp-tools \
		--no-experimental \
		--no-auto-update \
		--no-ask-user \
		--stream on \
		--silent \
		--model "claude-opus-4.6" \
		--effort "xhigh"

.PHONY: council-innovator-2
council-innovator-2:
	@gh copilot \
		--acp \
		--port 10002 \
		--yolo \
		--enable-all-github-mcp-tools \
		--no-experimental \
		--no-auto-update \
		--no-ask-user \
		--stream on \
		--silent \
		--model "GPT-5.4" \
		--effort "xhigh"

.PHONY: council-critic
council-critic:
	@gh copilot \
		--acp \
		--port 10003 \
		--yolo \
		--enable-all-github-mcp-tools \
		--no-experimental \
		--no-auto-update \
		--no-ask-user \
		--stream on \
		--silent \
		--model "claude-opus-4.6" \
		--effort "high"

.PHONY: council-clerk
council-clerk:
	@gh copilot \
		--acp \
		--port 10004 \
		--yolo \
		--enable-all-github-mcp-tools \
		--no-experimental \
		--no-auto-update \
		--no-ask-user \
		--stream on \
		--silent \
		--model "claude-opus-4.6" \
		--effort "high"

.PHONY: council-dreamer
council-dreamer:
	@gh copilot \
		--acp \
		--port 10005 \
		--yolo \
		--enable-all-github-mcp-tools \
		--no-experimental \
		--no-auto-update \
		--no-ask-user \
		--stream on \
		--silent \
		--model "claude-sonnet-4.5" \
		--effort "medium"

.PHONY: council-interactive
council-interactive:
	@gh copilot \
		--yolo \
		--enable-all-github-mcp-tools \
		--no-experimental \
		--no-auto-update \
		--stream on \
		--silent \
		--model "claude-opus-4.6" \
		--effort "high" \
		--add-dir "$(ROOT)"

# -----------------------------------------------------------------------------
# rsync push
# -----------------------------------------------------------------------------

.PHONY: rsync-push
rsync-push:
	@$(RSYNC) \
		--exclude='/.git' \
		--exclude='/.idea' \
		--exclude='/cache/*.zip' \
		--exclude='/work/*' \
		--exclude='/data/*' \
		--exclude='*.log' \
		--exclude='__pycache__' \
		--exclude='.pytest_cache' \
		--exclude='.ipynb_checkpoints' \
		'$(ROOT)/' \
		'$(REMOTE_HOST):$(REMOTE_PATH)'

.PHONY: rsync-push-copilot
rsync-push-copilot:
	@$(RSYNC) \
		'${HOME}/.copilot/session-state' \
		'$(REMOTE_HOST):.copilot/session-state'

# -----------------------------------------------------------------------------
# rsync pull
# -----------------------------------------------------------------------------

.PHONY: rsync-pull
rsync-pull:
	@$(RSYNC) \
		--rsh="ssh -o ClearAllForwardings=yes" \
		--exclude='/.git' \
		--exclude='/.idea' \
		--exclude='/cache/*.zip' \
		--exclude='/work/*' \
		--exclude='/data/*' \
		--exclude='*.log' \
		--exclude='__pycache__' \
		--exclude='.pytest_cache' \
		--exclude='.ipynb_checkpoints' \
		'$(REMOTE_HOST):$(REMOTE_PATH)' \
		'$(ROOT)/'
