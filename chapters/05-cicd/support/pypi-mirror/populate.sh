#!/usr/bin/env bash
# Download the exact wheels a lockfile pins, for the platforms we deploy to,
# into ./packages. Run it for every lockfile change, after reviewing the diff.
#
#   ./populate.sh ../bookshelf-ch5-solution/requirements-dev.lock
#
# pip runs inside the same Python image as the Dockerfile, so the result does
# not depend on the Python version or OS of the machine running this script.
set -euo pipefail

LOCKFILE=${1:?usage: populate.sh <lockfile>}
PYTHON_IMAGE=python:3.12.16-slim-trixie
here=$(cd "$(dirname "$0")" && pwd)
lockdir=$(cd "$(dirname "$LOCKFILE")" && pwd)
lockname=$(basename "$LOCKFILE")

mkdir -p "$here/packages"

docker run --rm \
  --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$lockdir/$lockname:/in/requirements.lock:ro" \
  -v "$here/packages:/packages" \
  "$PYTHON_IMAGE" sh -euc '
    # Runtime targets: CI runners and servers (x86_64), Apple Silicon and
    # ARM servers (aarch64). Wheels only: no sdists, so no code runs at
    # download time and nothing is compiled on the way in.
    for arch in x86_64 aarch64; do
      pip download --quiet --disable-pip-version-check \
        --requirement /in/requirements.lock --dest /packages \
        --only-binary=:all: --implementation cp --python-version 3.12 \
        --abi cp312 --abi abi3 --abi none \
        --platform "manylinux_2_28_$arch" --platform "manylinux_2_17_$arch" \
        --platform "manylinux2014_$arch" --platform any
    done
    # Build backend for "pip install -e ." (see [build-system] in pyproject.toml).
    pip download --quiet --disable-pip-version-check \
      --only-binary=:all: --dest /packages "setuptools==84.2.1"
  '

echo "$(find "$here/packages" -name '*.whl' | wc -l | tr -d ' ') wheels in $here/packages"
