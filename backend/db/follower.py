# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Follower relation.

A Follower object defines a relation between a user and a viewpoint.
If a user is a follower of a viewpoint, episodes added to the
viewpoint are shared with the user.

Each follower contains a set of labels which describe properties and
permissions. See the descriptions for each label in the header of the
Follower class.

  Follower: defines relation between a user and a viewpoint.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import logging

from tornado import gen

from viewfinder.backend.base import util
from viewfinder.backend.base.exceptions import PermissionError
from viewfinder.backend.db import vf_schema
from viewfinder.backend.db.accounting import Accounting
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.notification import Notification
from viewfinder.backend.db.range_base import DBRangeObject

@DBObject.map_table_attributes
class Follower(DBRangeObject):
  """Viewfinder follower data object."""
  __slots__ = []

  _table = DBObject._schema.GetTable(vf_schema.FOLLOWER)

  ADMIN = 'admin'
  """The follower can change the permissions of any other follower in the viewpoint."""

  CONTRIBUTE = 'contribute'
  """The follower can change viewpoint metadata, add new followers, and contribute content to
  the viewpoint.
  """

  PERSONAL = 'personal'
  """Photos in this viewpoint should be shown in the summary and day views of the follower."""

  REMOVED = 'removed'
  """This viewpoint has been removed from the follower's inbox and is no longer accessible.
  Quota should not be counted against the account. If all followers have marked a viewpoint
  'removed', then the viewpoint's resources may be garbage collected.  Followers with this
  label should not be able to add or view any content in the viewpoint.  Attempts to modify
  content should fail with a permission error. Attempts to view content should return empty
  content.
  """

  MUTED = 'muted'
  """Alerts for the associated viewpoint will not be sent to this follower."""

  HIDDEN = 'hidden'
  """Any "trap doors" to this viewpoint should *not* be shown in the summary view of the
  follower.
  """

  AUTOSAVE = 'autosave'
  """Any time photos are added to the viewpoint, they are automatically saved to this follower's
  default viewpoint.
  """

  UNREVIVABLE = 'unrevivable'
  """This label should be set only if REMOVED is also set. If it is set, then the follower
  cannot be revived when activity occurs in the followed viewpoint. Only another follower
  re-adding the user to the viewpoint will restore access.
  """

  PERMISSION_LABELS = [ADMIN, CONTRIBUTE]
  """Labels that specify what the follower is allowed to do in the viewpoint."""

  UNSETTABLE_LABLES = PERMISSION_LABELS + [REMOVED, UNREVIVABLE]
  """Labels that should never be directly set by an end user, but are instead indirectly set
  by various operations.
  """

  ALL_LABELS = PERMISSION_LABELS + [PERSONAL, REMOVED, HIDDEN, MUTED, UNREVIVABLE, AUTOSAVE]
  """Viewpoint permissions and modifiers that apply to the follower."""

  def __init__(self, user_id=None, viewpoint_id=None):
    super(Follower, self).__init__()
    self.user_id = user_id
    self.viewpoint_id = viewpoint_id

  def CanViewContent(self):
    """Returns true if the follower has not been REMOVED.  REMOVED followers are not allowed
    to view viewpoint content.
    """
    return Follower.REMOVED not in self.labels

  def CanAdminister(self):
    """Returns true if the follower has the ADMIN permission and hasn't been REMOVED."""
    return Follower.ADMIN in self.labels and Follower.REMOVED not in self.labels

  def CanContribute(self):
    """Returns true if the follower has the CONTRIBUTE permission and hasn't been REMOVED."""
    return Follower.CONTRIBUTE in self.labels and Follower.REMOVED not in self.labels

  def IsRemoved(self):
    """Returns true if the follower has the Follower.REMOVED label."""
    return Follower.REMOVED in self.labels

  def IsMuted(self):
    """Returns true if alerts should be suppressed for this follower."""
    return Follower.MUTED in self.labels

  def IsUnrevivable(self):
    """Returns true if the follower cannot be revived when activity on the followed viewpoint
    occurs.
    """
    return Follower.UNREVIVABLE in self.labels

  def ShouldAutoSave(self):
    """Returns true if photos added to the viewpoint should be automatically saved to this
    follower's default viewpoint.
    """
    return Follower.AUTOSAVE in self.labels

  def MakeMetadataDict(self):
    """Projects all follower attributes that the follower himself can see."""
    foll_dict = {'follower_id': self.user_id}
    util.SetIfNotNone(foll_dict, 'adding_user_id', self.adding_user_id)
    util.SetIfNotNone(foll_dict, 'viewed_seq', self.viewed_seq)
    if self.labels is not None:
      # Normalize labels property for easier testing.
      foll_dict['labels'] = sorted(self.labels)
    return foll_dict

  def MakeFriendMetadataDict(self):
    """Projects a subset of the follower attributes that should be provided to another user
    that is on the same viewpoint as this follower.
    """
    foll_dict = {'follower_id': self.user_id}
    util.SetIfNotNone(foll_dict, 'adding_user_id', self.adding_user_id)
    util.SetIfNotNone(foll_dict, 'follower_timestamp', self.timestamp)
    if self.IsUnrevivable():
      # Only project labels if the follower has left the viewpoint entirely.
      foll_dict['labels'] = [Follower.REMOVED, Follower.UNREVIVABLE]
    return foll_dict

  def SetLabels(self, new_labels):
    """Sets the labels attribute on the follower. This must be done with care in order to
    avoid security bugs such as allowing users to give themselves admin permissions, or
    allowing users to accidentally remove their right to see the viewpoint, or allowing a
    viewpoint to be removed without updating quota.

    TODO(Andy): Eventually we'll want more full-featured control over
                permissions.
    """
    new_labels = set(new_labels)
    new_unsettable_labels = new_labels.intersection(Follower.UNSETTABLE_LABLES)
    existing_labels = set(self.labels)
    existing_unsettable_labels = existing_labels.intersection(Follower.UNSETTABLE_LABLES)
    if new_unsettable_labels != existing_unsettable_labels:
      raise PermissionError('Permission and removed labels cannot be updated on the follower.')
    self.labels = new_labels

  @gen.coroutine
  def RemoveViewpoint(self, client, allow_revive=True):
    """Removes a viewpoint from a user's inbox, and its content will become inaccessible to
    this follower. If "allow_revive" is true, then the viewpoint will automatically be
    "revived" when there is new activity by other followers that have not removed it.

    Adds the REMOVED label to this follower object and updates the db. Caller should have already
    checked permissions to do this. Adds the UNREVIVABLE label if "allow_revive" is false.
    """
    if not self.IsRemoved():
      # If not removed, then UNREVIVABLE flag should never be set.
      assert not self.IsUnrevivable(), self

      # Add follower label and persist the change.
      self.labels.add(Follower.REMOVED)

    if not allow_revive:
      self.labels.add(Follower.UNREVIVABLE)

    yield gen.Task(self.Update, client)

  @classmethod
  @gen.coroutine
  def ReviveRemovedFollowers(cls, client, followers):
    """Removes the REMOVED labels from any followers which are not marked as UNREVIVABLE, and
    updates those records in the DB.
    """
    tasks = []
    for follower in followers:
      if follower.IsRemoved() and not follower.IsUnrevivable():
        follower.labels.remove(Follower.REMOVED)
        tasks.append(gen.Task(follower.Update, client))

    yield tasks
