# Viewfinder bash initialization script for AWS instances.
#
# source from init scripts and cron jobs:
#   source ${HOME}/viewfinder/scripts/viewfinder-prod.bash
#
# Support for non-bash shells is left as an exercise for the reader.

# Get the root of the hg checkout.
ROOT=$(dirname $(dirname ${BASH_SOURCE[0]}))

# Convert to absolute path
ROOT=$(cd $ROOT; pwd)

# VF_HOME is used to set the later variables and also in .hgrc
export VF_HOME=$ROOT

# Python environment.
export PATH=~/env/viewfinder/bin:$PATH
export PYTHONPATH=$VF_HOME/pythonpath:$PYTHONPATH

# Additional scripts.  Optional but convenient.
export PATH=$VF_HOME/scripts:$PATH
