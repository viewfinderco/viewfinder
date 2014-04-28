# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Centralized repository for all error messages.

Each error message has a unique short string identifier, such as "NO_USER_ACCOUNT". This
string may be examined by clients, so it cannot be changed without considering backwards-
compatibility.

Each error is defined in this file similar to this:

  ERROR_ID = 'An error has occurred.'

However, a post-definition step runs which re-maps each definition to the following:

  ERROR_ID = ErrorDef('ERROR_ID', 'An error has occurred.')

Expanding the ErrorDef allows callers to get the unique id of the error, as well as its
string format, all without needing to manually duplicate information in the error definitions.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

from collections import namedtuple

ErrorDef = namedtuple('ErrorDef', ['id', 'format'])


# --------------------------------------------------
# Authentication error definitions.
# --------------------------------------------------

NO_USER_ACCOUNT = 'We can\'t find your Viewfinder account. Are you sure you used %(account)s to sign up?'

ALREADY_REGISTERED = 'A Viewfinder account for %(account)s already exists. Try logging in.'

ALREADY_LINKED = 'Cannot link %(account)s to your Viewfinder account. It is already linked to another account.'

INVALID_VERIFY_VIEWFINDER = 'The access token obtained from /%(action)s/viewfinder cannot be used with ' \
                            '/verify/viewfinder.'

MERGE_REQUIRES_LOGIN = 'You must be logged in before you can merge or link.'

EXPIRED_LINK = 'The requested link has expired and can no longer be used.'

TOO_MANY_MESSAGES_DAY = 'We already sent too many %(message_type)s to %(identity_value)s. Try again in 24 hours.'

INCORRECT_ACCESS_CODE = 'Incorrect access code. Use the code we sent to %(identity_value)s.'

LOGIN_REQUIRES_REGISTER = 'You must register your account before you can log into it.'


# --------------------------------------------------
# Operation error definitions.
# --------------------------------------------------

INVALID_REMOVE_PHOTOS_VIEWPOINT = 'Cannot remove photos from viewpoint "%(viewpoint_id)s". Photos can only ' \
                                  'be removed from your own personal viewpoint.'

CANNOT_REMOVE_DEFAULT_FOLLOWER = 'Cannot remove followers from a default viewpoint.'

CANNOT_REMOVE_FOLLOWERS = 'User %(user_id)d does not have permission to remove followers from viewpoint ' \
                          '"%(viewpoint_id)s".'

CANNOT_REMOVE_THIS_FOLLOWER = 'Cannot remove user %(remove_id)d from viewpoint "%(viewpoint_id)s. Only the user ' \
                              'that originally added that user can remove.'

CANNOT_REMOVE_OLD_FOLLOWER = 'Cannot remove user %(remove_id)d from viewpoint "%(viewpoint_id)s. This user ' \
                             'was added more than 7 days ago.'

VIEWPOINT_NOT_FOUND = 'Viewpoint "%(viewpoint_id)s does not exist.'


# --------------------------------------------------
# Service API error definitions.
# --------------------------------------------------

INVALID_JSON_REQUEST = 'Invalid JSON request: %(request)s'

UPDATE_PWD_NOT_CONFIRMED = 'Password cannot be updated. The account was not recently confirmed via email or SMS.'

MERGE_COOKIE_NOT_CONFIRMED = 'User account %(user_id)d cannot be merged. The account was not recently confirmed ' \
                             'via email or SMS.'

UPLOAD_CONTACTS_EXCEEDS_LIMIT = 'Upload contacts exceeds the limit for total persisted contacts per user.'

BAD_CONTACT_SOURCE = 'Bad contact id.  Unrecognized or invalid contact_source: %(contact_source)s.'

MISSING_MERGE_SOURCE = 'Missing merge source. Either "source_user_cookie" or "source_identity" must be specified.'

BAD_IDENTITY = 'Identity "%(identity_key)s" does not exist.'

IDENTITY_NOT_CANONICAL = 'Identity "%(identity_key)s" is not in its canonical form.'


# --------------------------------------------------
# General error messages.
# --------------------------------------------------

MISSING_PARAMETER = 'Missing "%(name)s" query parameter.'

SERVICE_UNAVAILABLE = 'We are experiencing temporary technical difficulties. Please retry your request.'

UNSUPPORTED_ASSET_TYPE = 'Unsupported asset type: %(asset_type)s'


# Dynamically re-map each error definition value to an ErrorDef tuple.
for key, value in globals().items():
  if key not in ['__name__', '__file__', '__author__', 'ErrorDef']:
    globals()[key] = ErrorDef(key, value)
