# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Viewfinder settings.

These classes support the storage of any kind of user or application settings in a single
shared Settings table. For example, user settings can be stored alongside device settings
and internal application settings.

In order to add a new kind of settings, derive from the Settings class. Override the
_COLUMN_NAMES class attribute in order to specify which columns in the Settings table are
used by the new class. The base Settings class will only expose those columns, in order
to catch bugs where an attempt is made to access a column for the wrong settings group.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

from viewfinder.backend.base import util
from viewfinder.backend.db import vf_schema
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.range_base import DBRangeObject


@DBObject.map_table_attributes
class Settings(DBRangeObject):
  """Viewfinder settings data object."""
  __slots__ = []

  _table = DBObject._schema.GetTable(vf_schema.SETTINGS)

  # List of attribute names in the Settings table that can be read and written by this class. By
  # default, the base class loads all settings attributes, but a derived class can override this
  # field in order to specify a subset that it manages.
  _COLUMN_NAMES = None

  def __init__(self):
    col_names = self.__class__._COLUMN_NAMES + ['settings_id', 'group_name', '_version']
    columns = [self._table.GetColumn(name) for name in col_names] if col_names is not None else None
    super(Settings, self).__init__(columns=columns)


@DBObject.map_table_attributes
class AccountSettings(Settings):
  """Settings group that contains options and choices affecting a user account.

  Alert settings:
    - email_alerts: enum controlling when alert emails are sent; by default, no alert emails
                    are sent:
                      none: do not send alert emails.
                      on_share_new: send email when new conversation is started or joined.

    - sms_alerts: enum controlling when alert SMS messages are sent; by default, no alert SMS
                  messages are sent:
                    none: do not send alert SMS messages.
                    on_share_new: send SMS message when new conversation is started or joined.

    - push_alerts: enum controlling when notifications are pushed to the user's device(s); by
                   default no alerts are pushed:
                     none: do not push any alerts
                     all: push alerts on share_new, add_followers, share_existing, post_comment

  Storage settings:
    - storage_options: set of boolean options controlling photo storage:
                         use_cloud: cloud storage is enabled for the user account.
                         store_originals: originals are uploaded to the cloud.

  Marketing communication:
    - marketing: enum controlling when marketing communication is sent (default=all):
                   none: do not send marketing communications
                   all: send all marketing communications
  """
  GROUP_NAME = 'account'

  # Email alerts.
  EMAIL_ALERTS = 'email_alerts'
  EMAIL_NONE = 'none'
  EMAIL_ON_SHARE_NEW = 'on_share_new'
  ALL_EMAIL_ALERTS = [EMAIL_NONE, EMAIL_ON_SHARE_NEW]

  # SMS alerts.
  SMS_ALERTS = 'sms_alerts'
  SMS_NONE = 'none'
  SMS_ON_SHARE_NEW = 'on_share_new'
  ALL_SMS_ALERTS = [SMS_NONE, SMS_ON_SHARE_NEW]

  # Push alerts.
  PUSH_ALERTS = 'push_alerts'
  PUSH_NONE = 'none'
  PUSH_ALL = 'all'
  ALL_PUSH_ALERTS = [PUSH_NONE, PUSH_ALL]

  # Storage options.
  STORAGE_OPTIONS = 'storage_options'
  USE_CLOUD = 'use_cloud'
  STORE_ORIGINALS = 'store_originals'
  ALL_STORAGE_OPTIONS = [USE_CLOUD, STORE_ORIGINALS]

  # Marketing communication.
  MARKETING = 'marketing'
  MARKETING_NONE = 'none'
  MARKETING_ALL = 'all'
  ALL_MARKETING = [MARKETING_NONE, MARKETING_ALL]

  _COLUMN_NAMES = ['user_id', EMAIL_ALERTS, SMS_ALERTS, PUSH_ALERTS, STORAGE_OPTIONS, MARKETING, 'sms_count']
  """Names of columns that are accessible on this object."""

  _JSON_ATTRIBUTES = [EMAIL_ALERTS, SMS_ALERTS, STORAGE_OPTIONS]
  """Subset of attributes that are returned to the owning user in query_users."""

  def AllowMarketing(self):
    """Returns true if marketing communication is allowed to be sent."""
    return self.marketing != AccountSettings.MARKETING_NONE

  def MakeMetadataDict(self):
    """Project a subset of account settings attributes that can be provided to the user."""
    settings_dict = {}
    for attr_name in AccountSettings._JSON_ATTRIBUTES:
      value = getattr(self, attr_name, None)
      if isinstance(value, frozenset):
        util.SetIfNotEmpty(settings_dict, attr_name, list(value))
      else:
        util.SetIfNotNone(settings_dict, attr_name, value)

    return settings_dict

  @classmethod
  def ConstructSettingsId(cls, user_id):
    """Constructs the settings id used for user settings: us:<user_id>."""
    return 'us:%d' % user_id

  @classmethod
  def ConstructKey(cls, user_id):
    """Constructs a DBKey that refers to the account settings for the given user:
         (us:<user_id>, 'account').
    """
    return DBKey(AccountSettings.ConstructSettingsId(user_id), AccountSettings.GROUP_NAME)

  @classmethod
  def CreateForUser(cls, user_id, **obj_dict):
    """Creates a new AccountSettings object for the given user and populates it with the given
    attributes.
    """
    return AccountSettings.CreateFromKeywords(settings_id=AccountSettings.ConstructSettingsId(user_id),
                                              group_name=AccountSettings.GROUP_NAME,
                                              user_id=user_id,
                                              **obj_dict)

  @classmethod
  def QueryByUser(cls, client, user_id, col_names, callback, must_exist=True, consistent_read=False):
    """For the convenience of the caller, automatically creates the settings_id and group_name
    parameters for the call to the base Query method.
    """
    super(AccountSettings, cls).KeyQuery(client,
                                         AccountSettings.ConstructKey(user_id),
                                         col_names,
                                         callback,
                                         must_exist=must_exist,
                                         consistent_read=consistent_read)
