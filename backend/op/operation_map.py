# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""OperationMap instance for Viewfinder operations.

An operation map is a dictionary that maps from an operation method name string to an instance
of OpMapEntry. The Operation class uses this map to get information about an operation, such
as how to execute it and what migrators to use in order to change the message version of the
operation args.

This module defines the operation map for DB operations such as AddFollowersOp.Execute and
UnshareOp.Execute. When new DB operations are added, an entry must be added to this map.

Most Viewfinder operations (but not all) follow a similar pattern that assists in preserving
idempotency:

   Phase 1: CHECK
     Gather information about the state of the db before any mutations are done. Check pre-
     conditions, restrictions, and permissions that the operation requires. Set an operation
     checkpoint during this phase, and preserve any pre-mutation information that we need in
     order to execute identical checks and mutations during phases 2 - 3. Errors raised during
     this phase can cause a clean abort of the operation, since no mutations have yet occurred.

   Phase 2: UPDATE
     Perform any updates to the database required by the operation. If the operation is
     restarted, the exact same mutations must be made during this phase.

   Phase 3: ACCOUNT
     Perform any changes to user and viewpoint accounting required by the operation. If
     the operation is restarted, the exact same changes must be made during this phase.

   Phase 4: NOTIFY
     Create any notifications required by the operation. Multiple notifications may be
     made for the same operation, even to the same user. If the operation is restarted,
     it is permissible for new notifications to be created (i.e. creation of notifications
     need not be idempotent).
"""

from viewfinder.backend.db.comment import Comment
from viewfinder.backend.db.device import Device
from viewfinder.backend.db.friend import Friend
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.subscription import Subscription
from viewfinder.backend.db.user import User
from viewfinder.backend.db.user_photo import UserPhoto
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.add_followers_op import AddFollowersOperation
from viewfinder.backend.op.build_archive_op import BuildArchiveOperation
from viewfinder.backend.op.create_prospective_op import CreateProspectiveOperation
from viewfinder.backend.op.fetch_contacts_op import FetchContactsOperation
from viewfinder.backend.op.hide_photos_op import HidePhotosOperation
from viewfinder.backend.op.link_identity_op import LinkIdentityOperation
from viewfinder.backend.op.merge_accounts_op import MergeAccountsOperation
from viewfinder.backend.op.remove_contacts_op import RemoveContactsOperation
from viewfinder.backend.op.remove_followers_op import RemoveFollowersOperation
from viewfinder.backend.op.remove_photos_op import RemovePhotosOperation
from viewfinder.backend.op.remove_viewpoint_op import RemoveViewpointOperation
from viewfinder.backend.op.op_manager import OpMapEntry
from viewfinder.backend.op.post_comment_op import PostCommentOperation
from viewfinder.backend.op.register_user_op import RegisterUserOperation
from viewfinder.backend.op.save_photos_op import SavePhotosOperation
from viewfinder.backend.op.share_existing_op import ShareExistingOperation
from viewfinder.backend.op.share_new_op import ShareNewOperation
from viewfinder.backend.op.unshare_op import UnshareOperation
from viewfinder.backend.op.update_episode_op import UpdateEpisodeOperation
from viewfinder.backend.op.update_follower_op import UpdateFollowerOperation
from viewfinder.backend.op.update_viewpoint_op import UpdateViewpointOperation
from viewfinder.backend.op.upload_contacts_op import UploadContactsOperation
from viewfinder.backend.op.upload_episode_op import UploadEpisodeOperation


def _CreateDbOperationMap(entry_list):
  """Create an operation map from a list of OpMapEntry objects. Note
  that operation handlers must be classmethods, not staticmethods.
  """
  map = dict()
  for entry in entry_list:
    handler = entry.handler
    method_str = handler.im_self.__name__ + '.' + handler.im_func.__name__
    map[method_str] = entry
  return map


def _ScrubItem(dict, item_name):
  """Replace value of dict[item_name] with scrubbed text."""
  if item_name in dict:
    dict[item_name] = '...scrubbed %s bytes...' % len(dict[item_name])


def _ScrubForClass(cls, message):
  for key in message:
    if cls.ShouldScrubColumn(key):
      _ScrubItem(message, key)


def _ScrubPostComment(op_args):
  """Scrub the comment message from the logs."""
  _ScrubForClass(Comment, op_args['comment'])


def _ScrubRegisterUser(op_args):
  _ScrubForClass(Identity, op_args['ident_dict'])


def _ScrubShareNew(op_args):
  """Scrub the viewpoint title from the logs."""
  _ScrubForClass(Viewpoint, op_args['viewpoint'])


def _ScrubUpdateDevice(op_args):
  """Scrub the device name from the logs."""
  _ScrubForClass(Device, op_args['device_dict'])


def _ScrubUpdateUser(op_args):
  """Scrub the pwd_hash and salt from the logs."""
  _ScrubForClass(User, op_args['user_dict'])


def _ScrubUpdateViewpoint(op_args):
  """Scrub the viewpoint title from the logs."""
  _ScrubForClass(Viewpoint, op_args['vp_dict'])


DB_OPERATION_MAP = _CreateDbOperationMap([
  OpMapEntry(AddFollowersOperation.Execute),
  OpMapEntry(BuildArchiveOperation.Execute),
  OpMapEntry(CreateProspectiveOperation.Execute),
  OpMapEntry(Device.UpdateOperation, scrubber=_ScrubUpdateDevice),
  OpMapEntry(FetchContactsOperation.Execute),
  OpMapEntry(Friend.UpdateOperation),
  OpMapEntry(HidePhotosOperation.Execute),
  OpMapEntry(Identity.UnlinkIdentityOperation),
  OpMapEntry(LinkIdentityOperation.Execute),
  OpMapEntry(MergeAccountsOperation.Execute),
  OpMapEntry(Photo.UpdateOperation),
  OpMapEntry(PostCommentOperation.Execute, scrubber=_ScrubPostComment),
  OpMapEntry(RegisterUserOperation.Execute, scrubber=_ScrubRegisterUser),
  OpMapEntry(RemoveContactsOperation.Execute),
  OpMapEntry(RemoveFollowersOperation.Execute),
  OpMapEntry(RemovePhotosOperation.Execute),
  OpMapEntry(RemoveViewpointOperation.Execute),
  OpMapEntry(SavePhotosOperation.Execute),
  OpMapEntry(ShareExistingOperation.Execute),
  OpMapEntry(ShareNewOperation.Execute),
  OpMapEntry(Subscription.RecordITunesTransactionOperation),
  OpMapEntry(UnshareOperation.Execute),
  OpMapEntry(UpdateEpisodeOperation.Execute),
  OpMapEntry(UpdateFollowerOperation.Execute),
  OpMapEntry(UpdateViewpointOperation.Execute),
  OpMapEntry(UploadContactsOperation.Execute),
  OpMapEntry(UploadEpisodeOperation.Execute),
  OpMapEntry(User.UpdateOperation, scrubber=_ScrubUpdateUser),
  OpMapEntry(User.TerminateAccountOperation),
  OpMapEntry(UserPhoto.UpdateOperation),
  OpMapEntry(Viewpoint.UpdateOperation, scrubber=_ScrubUpdateViewpoint),
  ])
