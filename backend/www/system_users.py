# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Creates and loads Viewfinder system users.

"CreateSystemUsers" is manually called once in order to initially populate the database with
system users. Then, just before server startup, the system users are loaded into memory.

  - There are 4 users used in the "Welcome to Viewfinder" conversation that every new user gets.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

import base64
import json
import os
import sys

from copy import deepcopy
from tornado import gen, options
from tornado.httpclient import AsyncHTTPClient
from viewfinder.backend.base import util
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.db_client import DBClient
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.settings import AccountSettings
from viewfinder.backend.db.user import User
from viewfinder.backend.resources.resources_mgr import ResourcesManager
from viewfinder.backend.storage.object_store import ObjectStore
from viewfinder.backend.www.service import UploadEpisode


# User objects for the welcome users.
NARRATOR_USER = None

# Dicts used to create the welcome users.
_NARRATOR_USER_DICT = {'name': 'Viewfinder',
                       'given_name': 'Viewfinder',
                       'email': 'narrator@emailscrubbed.com'}

NARRATOR_UPLOAD_PHOTOS = {'headers': {'synchronous': True},
                          'activity': {'timestamp': 1378337081.577504},
                          'episode': {'timestamp': 1330040031},
                          'photos': [{'name': 'beach_c4',
                                      'tn_md5': 'dfccde58ec03f865521a0e731a26a879',
                                      'med_size': 37792,
                                      'timestamp': 1330040031,
                                      'full_md5': 'ebbac5df3c3c8fa6b9d4807546c9383b',
                                      'placemark': {'iso_country_code': 'AU',
                                                    'thoroughfare': 'Marina Terrace',
                                                    'locality': 'Hamilton Island',
                                                    'country': 'Australia',
                                                    'state': 'Queensland',
                                                    'sublocality': 'Whitsunday'},
                                      'orig_md5': '4417fc583bba0415828e7550bfcd4929',
                                      'med_md5': 'b213c48022d41124003377c6aa64a20d',
                                       'aspect_ratio': 1.5,
                                      'location': {'latitude':-20.34851,
                                                   'longitude': 148.9560433333333,
                                                   'accuracy': 0.0},
                                       'content_type': 'image/jpeg',
                                      'tn_size': 5627,
                                      'orig_size': 774908,
                                      'full_size': 118663},
                                     {'name': 'beach_a1',
                                      'tn_md5': 'e94211e5e63778b40c45e51b3c2b19c9',
                                      'med_size': 31150,
                                      'timestamp': 1329596931,
                                      'full_md5': 'a7f31e31cdbeba38715271e8795d8499',
                                      'placemark': {'iso_country_code': 'AU',
                                                    'country': 'Australia',
                                                    'state': 'New South Wales'},
                                      'orig_md5': 'de09b4b75ad0e128e22043e04b85b7c8',
                                      'med_md5': 'dbc83ca74939a733bd02a5b3d3d46dd9',
                                      'aspect_ratio': 1.5,
                                      'location': {'latitude':-28.65277,
                                                   'longitude': 153.6280016666667,
                                                   'accuracy': 0.0},
                                      'content_type': 'image/jpeg',
                                      'tn_size': 5551,
                                      'orig_size': 770447,
                                      'full_size': 96052},
                                     {'name': 'beach_a2',
                                      'tn_md5': 'a26c22b3ed2082f2a6a973ebeba33f26',
                                      'med_size': 35341,
                                      'timestamp': 1329590091,
                                      'full_md5': 'e8530cb5286b239e12a52206873c0535',
                                      'placemark': {'iso_country_code': 'AU',
                                                    'country': 'Australia',
                                                    'state': 'New South Wales'},
                                      'orig_md5': '5ee99fc13e013b3a0c8bdd1e9a9aec6c',
                                      'med_md5': 'b711b419907aed1bf2f018322fab05ed',
                                      'aspect_ratio': 0.6666666865348816,
                                      'location': {'latitude':-28.65277,
                                                   'longitude': 153.6280016666667,
                                                   'accuracy': 0.0},
                                      'content_type': 'image/jpeg',
                                      'tn_size': 5563,
                                      'orig_size': 788837,
                                      'full_size': 116777},
                                     {'name': 'beach_a3',
                                      'tn_md5': 'a42a0599d8f5d3b1e010fad0be8223f8',
                                      'med_size': 38972,
                                      'timestamp': 1329597411,
                                      'full_md5': '5a95702fbd3e9c28f287711206776a88',
                                      'placemark': {'iso_country_code': 'AU',
                                                    'country': 'Australia',
                                                    'state': 'New South Wales'},
                                      'orig_md5': '5aede0de95b19d2e24628bf301ccb84d',
                                      'med_md5': '4c8d981e7fa30d179ae3e18e99229db5',
                                      'aspect_ratio': 1.5,
                                      'location': {'latitude':-28.65277,
                                                   'longitude': 153.6280016666667,
                                                   'accuracy': 0.0},
                                      'content_type': 'image/jpeg',
                                      'tn_size': 6162,
                                      'orig_size': 731095,
                                      'full_size': 116030}]}

NARRATOR_UPLOAD_PHOTOS_2 = {'headers': {'synchronous': True},
                            'activity': {'timestamp': 1378337081.577504},
                            'episode': {'timestamp': 1330068660},
                            'photos': [{'name': 'street_art_1',
                                        'tn_md5': 'c13f7b3834cff6c05399afc0a2849962',
                                        'med_size': 68842,
                                        'timestamp': 1378238091,
                                        'full_md5': 'e590c7a3a499576ce26edc591ab5c02e',
                                        'placemark': {'iso_country_code': 'US',
                                                      'thoroughfare': 'Lafayette St',
                                                      'locality': 'New York',
                                                      'country': 'United States',
                                                      'subthoroughfare': '76',
                                                      'state': 'New York',
                                                      'sublocality': 'Civic Center'},
                                        'orig_md5': 'f60647a580b5ffd289d7883cc7304f05',
                                        'med_md5': '6f56107b2f1cf32f1dc7fb7b9fe75ce8',
                                        'aspect_ratio': 0.6666666865348816,
                                        'location': {'latitude': 40.71702333333333,
                                                     'longitude':-74.00212635,
                                                     'accuracy': 0.0},
                                        'content_type': 'image/jpeg',
                                        'tn_size': 6766,
                                        'orig_size': 293220,
                                        'full_size': 232654},
                                       {'name': 'street_art_2',
                                        'tn_md5': 'acea50019d153ba4a0800336827b7cf5',
                                        'med_size': 70651,
                                        'timestamp': 1378240431,
                                        'full_md5': 'a065d8d88c60c1974938a71b691bfd5d',
                                        'placemark': {'iso_country_code': 'US',
                                                      'thoroughfare': 'Lafayette St',
                                                      'locality': 'New York',
                                                      'country': 'United States',
                                                      'subthoroughfare': '76',
                                                      'state': 'New York',
                                                      'sublocality': 'Civic Center'},
                                        'orig_md5': '7c8b96a8acd3c18a3d3ad7cdd89cc9dd',
                                        'med_md5': 'a5942e651f9c5fa67eb67512638b690c',
                                        'aspect_ratio': 1,
                                        'location': {'latitude': 40.71702333333333,
                                                     'longitude':-74.00212635,
                                                     'accuracy': 0.0},
                                        'content_type': 'image/jpeg',
                                        'tn_size': 7390,
                                        'orig_size': 135770,
                                        'full_size': 114125}]}

NARRATOR_UPLOAD_PHOTOS_3 = {'headers': {'synchronous': True},
                            'activity': {'timestamp': 1378332211.326277},
                            'episode': {'timestamp': 590899320},
                            'photos': [{'name': 'party_1',
                                        'tn_md5': '3d5fb49c6f33797b3cdac21da89c785b',
                                        'med_size': 61665,
                                        'timestamp': 1371593871,
                                        'full_md5': '40433e5f040bb86539bf03ea89ae10b7',
                                        'placemark': {'iso_country_code': 'US',
                                                      'thoroughfare': 'Broadway',
                                                      'locality': 'New York',
                                                      'country': 'United States',
                                                      'subthoroughfare': '670',
                                                      'state': 'New York',
                                                      'sublocality': 'Greenwich Village'},
                                        'orig_md5': '0ffd5954ed4025ecf8613cb3c2313de8',
                                        'med_md5': '2c2a74d643acf022acca55501c304543',
                                        'aspect_ratio': 1.5,
                                        'location': {'latitude': 40.72718333333334,
                                                     'longitude':-73.99460666666667,
                                                     'accuracy': 0.0},
                                         'content_type': 'image/jpeg',
                                        'tn_size': 8237,
                                        'orig_size': 895996,
                                        'full_size': 172343},
                                       {'name': 'party_3',
                                        'tn_md5': 'af462e6d8239848fc743f259bede4867',
                                        'med_size': 50530,
                                        'timestamp': 1371595311,
                                        'full_md5': '065713103f4032b02b7422ed79415525',
                                        'placemark': {'iso_country_code': 'US',
                                                      'thoroughfare': 'Broadway',
                                                      'locality': 'New York',
                                                      'country': 'United States',
                                                      'subthoroughfare': '670',
                                                      'state': 'New York',
                                                      'sublocality': 'Greenwich Village'},
                                        'orig_md5': 'f95e9353605279ca64b604efc86c0699',
                                        'med_md5': 'f60a48ffee94442967fc8c3f24ff32de',
                                        'aspect_ratio': 1,
                                        'location': {'latitude': 40.72718333333334,
                                                     'longitude':-73.99460666666667,
                                                     'accuracy': 0.0},
                                        'content_type': 'image/jpeg',
                                        'tn_size': 9075,
                                        'orig_size': 273130,
                                        'full_size': 140349},
                                       {'name': 'party_4',
                                        'tn_md5': '49d9c13a8ced18825ebd06336b1e43ba',
                                        'med_size': 46190,
                                        'timestamp': 1371602511,
                                        'full_md5': '189ef8e05d75235ee96b3a4c3010bee0',
                                        'placemark': {'iso_country_code': 'US',
                                                      'thoroughfare': 'Broadway',
                                                      'locality': 'New York',
                                                      'country': 'United States',
                                                      'subthoroughfare': '670',
                                                      'state': 'New York',
                                                      'sublocality': 'Greenwich Village'},
                                        'orig_md5': 'f3c56e2d81641ac80416b83c94f8154b',
                                        'med_md5': '805b888aafef57780ef644ad1237883c',
                                        'aspect_ratio': 1.5,
                                        'location': {'latitude': 40.72718333333334,
                                                     'longitude':-73.99460666666667,
                                                     'accuracy': 0.0},
                                        'content_type': 'image/jpeg',
                                        'tn_size': 6990,
                                        'orig_size': 256382,
                                        'full_size': 131818},
                                        ]}

@gen.coroutine
def LoadSystemUsers(client):
  """Loads all system users into memory before the server starts."""
  @gen.coroutine
  def _LoadUser(user_dict):
    identity_key = 'Email:%s' % user_dict['email']
    identity = yield gen.Task(Identity.Query, client, identity_key, None, must_exist=False)
    if identity is None or identity.user_id is None:
      raise gen.Return(None)

    user = yield gen.Task(User.Query, client, identity.user_id, None)
    raise gen.Return(user)

  global NARRATOR_USER
  NARRATOR_USER = yield _LoadUser(_NARRATOR_USER_DICT)

  # Set all asset ids if users exist.
  if NARRATOR_USER is not None:
    yield _SetWelcomeIds(NARRATOR_USER, NARRATOR_UPLOAD_PHOTOS)
    yield _SetWelcomeIds(NARRATOR_USER, NARRATOR_UPLOAD_PHOTOS_2)
    yield _SetWelcomeIds(NARRATOR_USER, NARRATOR_UPLOAD_PHOTOS_3)


@gen.coroutine
def CreateSystemUsers(client):
  """Creates all system users, including uploading any photos they should own. This should be
  done manually by running this file at the command line in order to populate production:

    python system_users.py --devbox

  This function is idempotent, and can be run repeatedly if it fails.
  """
  @gen.coroutine
  def _CreateUser(user_dict):
    """Creates a single user from the provided user_dict."""
    identity_key = 'Email:%s' % user_dict['email']
    identity = yield gen.Task(Identity.Query, client, identity_key, None, must_exist=False)

    # Get existing user id and web device id, if they exist.
    user_id = None
    if identity is not None and identity.user_id is not None:
      user = yield gen.Task(User.Query, client, identity.user_id, None, must_exist=False)
      if user is not None:
        user_id = user.user_id
        webapp_dev_id = user.webapp_dev_id

    if user_id is None:
      # Allocate new user id and web device id.
      user_id, webapp_dev_id = yield User.AllocateUserAndWebDeviceIds(client)

    # Create prospective user.
    user, identity = yield gen.Task(User.CreateProspective,
                                    client,
                                    user_id,
                                    webapp_dev_id,
                                    identity_key,
                                    util.GetCurrentTimestamp())

    # Register the user.
    user_dict = deepcopy(user_dict)
    user_dict['user_id'] = user_id
    user = yield gen.Task(User.Register,
                          client,
                          user_dict,
                          {'key': identity_key, 'authority': 'Viewfinder'},
                          util.GetCurrentTimestamp(),
                          rewrite_contacts=False)

    # Turn off email alerts.
    settings = AccountSettings.CreateForUser(user_id, email_alerts=AccountSettings.EMAIL_NONE)
    yield gen.Task(settings.Update, client)

    # Make this a system user so that client will not add it to contacts.
    yield user.MakeSystemUser(client)

    raise gen.Return(user)

  # Create each user account.
  global NARRATOR_USER
  NARRATOR_USER = yield _CreateUser(_NARRATOR_USER_DICT)

  # Upload welcome photos to users' default viewpoints.
  http_client = AsyncHTTPClient()
  yield _UploadWelcomePhotos(http_client, client, NARRATOR_USER, NARRATOR_UPLOAD_PHOTOS)
  yield _UploadWelcomePhotos(http_client, client, NARRATOR_USER, NARRATOR_UPLOAD_PHOTOS_2)
  yield _UploadWelcomePhotos(http_client, client, NARRATOR_USER, NARRATOR_UPLOAD_PHOTOS_3)


@gen.coroutine
def _SetWelcomeIds(user, upload_request):
  """Assigns activity, episode, and photo ids for all welcome conversation requests. Assets
  are assigned unique ids starting at 1.
  """
  # Construct the activity id.
  unique_id = 1
  act_dict = upload_request['activity']
  act_dict['activity_id'] = Activity.ConstructActivityId(act_dict['timestamp'], user.webapp_dev_id, unique_id)
  unique_id += 1

  # Construct the episode id.
  ep_dict = upload_request['episode']
  ep_dict['episode_id'] = Episode.ConstructEpisodeId(ep_dict['timestamp'], user.webapp_dev_id, unique_id)
  unique_id += 1

  # Construct the photo ids.
  for ph_dict in upload_request['photos']:
    # Create metadata for each photo.
    ph_dict['photo_id'] = Photo.ConstructPhotoId(ph_dict['timestamp'], user.webapp_dev_id, unique_id)
    unique_id += 1


@gen.coroutine
def _UploadWelcomePhotos(http_client, client, user, upload_request):
  """Uploads a set of photos that will be used in the new user welcome conversation. These
  photos are uploaded to the given user account. "upload_request" is in the UPLOAD_EPISODE_REQUEST
  format in json_schema.py, except:

    1. Activity, episode, and photo ids are added by this method.
    2. Each photo dict must contain an additional "name" field which gives the start of the
       filename of a jpg file in the backend/resources/welcome directory. Three files must
       exist there, in this format: <name>_full.jpg, <name>_med.jpg, <name>_tn.jpg.
  """
  obj_store = ObjectStore.GetInstance(ObjectStore.PHOTO)
  welcome_path = os.path.join(ResourcesManager.Instance().resources_path, 'welcome')

  # Set the ids of all activities, episodes, and photos in the welcome conversation.
  yield _SetWelcomeIds(user, upload_request)

  # Get copy and strip out names, which UploadEpisode chokes on.
  upload_request = deepcopy(upload_request)

  # Directly call the service API in order to upload the photo.
  upload_request_copy = deepcopy(upload_request)
  [ph_dict.pop('name') for ph_dict in upload_request_copy['photos']]
  upload_response = yield UploadEpisode(client, obj_store, user.user_id, user.webapp_dev_id, upload_request_copy)

  # Upload photo to blob store (in various formats).
  for request_ph_dict, response_ph_dict in zip(upload_request['photos'], upload_response['photos']):
    for format in ('full', 'med', 'tn'):
      # Get the photo bits from disk.
      f = open(os.path.join(welcome_path, '%s_%s.jpg' % (request_ph_dict['name'], format)), 'r')
      image_data = f.read()
      f.close()

      photo_url = response_ph_dict[format + '_put_url']
      content_md5 = base64.b64encode(request_ph_dict[format + '_md5'].decode('hex'))
      headers = {'Content-Type': 'image/jpeg', 'Content-MD5': content_md5}

      validate_cert = not options.options.fileobjstore
      response = yield gen.Task(http_client.fetch,
                                photo_url,
                                method='PUT',
                                body=image_data,
                                follow_redirects=False,
                                validate_cert=validate_cert,
                                headers=headers)
      if response.code != 200:
        raise Exception('Cannot upload photo "%s". HTTP error code %d. Is server running and accessible?' %
                        (request_ph_dict['photo_id'], response.code))

if __name__ == '__main__':
  # Run this file in order to create system users. Here is the command for populating the local
  # data store for testing (or just start local-viewfinder and it will populate itself):
  #   python system_users.py --devbox --domain=goviewfinder.com --localdb=True --fileobjstore=True
  @gen.coroutine
  def _CreateSystemUsers():
    yield CreateSystemUsers(DBClient.Instance())

  @gen.coroutine
  def _CreateFormats():
    """Used to set up initial photos."""
    obj_store = ObjectStore.GetInstance(ObjectStore.PHOTO)
    client = DBClient.Instance()
    http_client = AsyncHTTPClient()

    for photo_id, name in [('pgAZn77bJ-Kc', 'beach_c4'),
                           ('pgAzpz7bJ-Mc', 'beach_a1'),
                           ('pgB-Fh7bJ-Mg', 'beach_a2'),
                           ('pgAzo67bJ-MV', 'beach_a3'),
                           ('pgB-pj7bJ-Mo', 'beach_a4'),
                           ('pgAvIa7bJ-MN', 'beach_b1'),
                           ('pgAuoQ7bJ-MF', 'beach_b2'),
                           ('pgAtwd7bJ-M7', 'beach_b3'),

                           ('pgAaOJ7bJ-Kw', 'beach_c1'),
                           ('pgA_vm7bJ-Ko', 'beach_c2'),
                           ('pgAZna7bJ-Kk', 'beach_c3'),

                           ('pgAW0x7bJ-KV', 'beach_d1'),
                           ('pgAUMm7bJ-KN', 'beach_d2'),

                           ('pfYwYR7bJ-KJ', 'party_1'),
                           ('pfYwTk7bJ-KF', 'party_2'),
                           ('pfYwSo7bJ-K7', 'party_3'),
                           ('pfYw0g7bJ-K-', 'party_4'),
                           ('pfYvoK7bJ-Jw', 'party_5'),
                           ('pfYvhI7bJ-Jo', 'party_6'),

                           ('prHKwa7bJ-N30', 'gone_fishing_1'),
                           ('prBUtl7bJ-Mw', 'gone_fishing_2'),

                           ('pfSb0S7bJ-Jk', 'street_art_1'),
                           ('pfSasJ7bJ-Jc', 'street_art_2')]:

      photo = yield Photo.Query(client, photo_id, None)
      photo_dict = photo._asdict()
      photo_dict['name'] = name
      del photo_dict['photo_id']
      del photo_dict['user_id']
      del photo_dict['_version']
      del photo_dict['episode_id']
      print json.dumps(photo_dict, indent=True)

      for suffix, format in [('.f', 'full'), ('.m', 'med'), ('.t', 'tn')]:
        url = obj_store.GenerateUrl('%s%s' % (photo_id, suffix))
        response = yield http_client.fetch(url, method='GET')

        welcome_path = os.path.join(ResourcesManager.Instance().resources_path, 'welcome')
        f = open(os.path.join(welcome_path, '%s_%s.jpg' % (name, format)), 'w')
        f.write(response.body)
        f.close()

  from viewfinder.backend.www import www_main
  sys.exit(www_main.InitAndRun(_CreateSystemUsers))
  #sys.exit(www_main.InitAndRun(_CreateFormats))
