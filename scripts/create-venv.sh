#!/usr/bin/env bash
set -e

if [[ -z "${PIP_INSTALL}" ]]; then
    PIP_INSTALL='install --upgrade'
fi

# Directory of *this* script
this_dir="$( cd "$( dirname "$0" )" && pwd )"
src_dir="$(realpath "${this_dir}/..")"

# -----------------------------------------------------------------------------

venv="${src_dir}/.venv"
download="${src_dir}/download"

# -----------------------------------------------------------------------------

: "${PYTHON=python3}"

if [[ ! -d "${venv}" ]]; then
    # Create virtual environment
    echo "Creating virtual environment at ${venv}"
    "${PYTHON}" -m venv "${venv}"
fi

source "${venv}/bin/activate"

# Directory where pre-compiled binaries will be installed
mkdir -p "${venv}/tools"

# Install Python dependencies
echo 'Installing Python dependencies'
pip3 ${PIP_INSTALL} pip
pip3 ${PIP_INSTALL} wheel setuptools

echo 'Installing requirements'
pip3 ${PIP_INSTALL} -f "${download}" -r requirements.txt

pip3 ${PIP_INSTALL} -f "${download}" -r requirements_dev.txt \
    || echo 'Failed to install development requirements'

# -----------------------------------------------------------------------------

echo "OK"
