#!/bin/bash
# A script to pull changes from the main repository and all submodules.

echo "Pulling changes for the main repository..."
git pull

echo "Updating all submodules..."
git submodule update --remote --merge

echo "All repositories are now up to date."
