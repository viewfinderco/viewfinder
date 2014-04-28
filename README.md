Viewfinder
==========

Setup
-----

We use subrepositories, so after cloning (or pulling any change that includes a change to
the subrepository), you must run

    $ git submodule update --init

Many of the following scripts require certain `PATH` entries or other environment variables.
Set them up with the following (this is intended to be run from `.bashrc` or other shell
initialization scripts; if you do not install it there you will need to repeat this command
in each new terminal):

    $ source scripts/viewfinder.bash

Server
------

To install dependencies (into `~/envs/vf-dev`), run

    $ update-environment

To run unit tests:

    $ run-tests

TODO: add ssl certificates and whatever else local-viewfinder needs, and document running it.

iOS client
----------

Our Xcode project files are generated with `gyp`.  After checking out the code
(and after any pull in which a `.gyp` file changed), run

    $ generate-projects.sh

Open the workspace containing the project, *not* the generated project itself:

    $ open clients/ios/ViewfinderWorkspace.xcworkspace

Android client
--------------

The android client is **unfinished**.  To build it, run

    $ generate-projects-android.sh
    $ vf-android.sh build
