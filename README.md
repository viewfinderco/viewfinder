Viewfinder
==========

This is the complete source for the Viewfinder server and iOS and
Android apps as they existed at the time the Viewfinder service was
shut down. We're releasing this code in the hopes that it can be of
utility to others, either as an archaeological resource or to pick up
the baton and start running with the Viewfinder vision again.

The Viewfinder engineers' days are now filled with other priorities
and we won't be able to provide support or bug fixes for this
code. The code is not as clean nor as well tested as you might find in
other open source projects. Yet it is the reality of what was produced
by a startup.

That said, there is quite a bit of interesting code to look at:

* The Viewfinder server provides a structured database schema with a
  variety of indexing options on top of Amazon's DynamoDB. See
  [schema.py](backend/db/schema.py) and
  [indexers.py](backend/db/indexers.py). Also take a look at the
  [operation.py](backend/db/operation.py) which provides at least once
  execution of idempotent operations.

* The server also provided support for versioning at both the database
  and protocol levels. See [db/versions.py](backend/db/versions.py),
  [base/message.py](backend/base/message.py) and
  [www/json_schema.py](backend/www/json_schema.py).q

* The [ViewfinderTool](clients/ios/Source/ViewfinderTool.h) required
  some nifty maths and fancy OpenGL graphics to implement. What is the
  fastest way to draw a circular gradient? Our answer was to
  approximate one using triangle fans and very simple and fast color
  interpolation in a shader.

* The Viewfinder Client uses [LevelDB]
  (https://code.google.com/p/leveldb/) for all local metadata
  storage. While arguably not as convenient as CoreData, we found
  LevelDB to be easy to use and very very fast. See
  [DB.h](clients/shared/DB.h).

* How to detect duplicate and near duplicate images from the iOS
  camera roll? Perceptual fingerprints. See
  [ImageFingerprint.h](clients/ios/Source/ImageFingerprint.h) and
  [ImageIndex.h](clients/shared/ImageIndex.h).

* Need a full text search engine that can work on a mobile device? We
  built one on top of LevelDB that we used for both searching for
  contacts and searching for photos. See
  [FullTextIndex.h](clients/shared/FullTextIndex.h).

* We used [GYP](https://code.google.com/p/gyp/) for generating Xcode
  project files and Android build files. GYP is awesome and removed
  the serious headache during iOS development of how to handle merge
  conflicts in Xcode project files. And GYP facilitated sharing a
  large [body of code](clients/shared) between the iOS and Android
  code bases.

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
