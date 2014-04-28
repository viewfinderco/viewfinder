# Dummy setup.py file because tox requires one.  Doesn't actually do anything.
import distutils.core
# import setuptools for a side effect: patches a distutils bug with
# broken symlinks.
import setuptools
distutils.core.setup(name='viewfinder')
