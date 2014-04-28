#!/bin/sh

set -e

apt-get update

APT_PACKAGES="
build-essential
libcurl4-openssl-dev
python-pip
python-dev
swig
"

apt-get -y install $APT_PACKAGES

PIP_PACKAGES="
virtualenv
tox
"

pip install $PIP_PACKAGES

# Link tox.ini into the home directory so you can run tox immediately
# after ssh'ing in without cd'ing to /vagrant (since cd'ing to /viewfinder
# gets the wrong config)
ln -sf /vagrant/tox.ini ~vagrant/tox.ini
