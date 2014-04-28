# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder base operation.

ViewfinderOperation is the base class for all other Viewfinder operations. It contains code
that is common across at least two derived operations.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

from copy import deepcopy
from tornado import gen
from viewfinder.backend.base.exceptions import InvalidRequestError, PermissionError
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.user import User


class ViewfinderOperation(object):
  """Base class for other Viewfinder operations, containing common code."""
  def __init__(self, client):
    self._client = client
    self._op = Operation.GetCurrent()

  @classmethod
  @gen.coroutine
  def _CheckEpisodePostAccess(cls, action, client, user_id, ep_ph_ids_list):
    """Ensures that given user has access to the set of episodes and photos in "ep_ph_ids_list",
    which is a list of (episode_id, photo_ids) tuples.

    Returns list of (episode, posts) tuples that corresponds to "ep_ph_ids_list".
    """
    # Gather db keys for all source episodes and posts, and check for duplicate episodes and photos.
    episode_keys = []
    post_keys = []
    for episode_id, photo_ids in ep_ph_ids_list:
      episode_keys.append(DBKey(episode_id, None))
      for photo_id in photo_ids:
        post_keys.append(DBKey(episode_id, photo_id))

    # Query for all episodes and posts in parallel and in batches.
    episodes, posts = yield [gen.Task(Episode.BatchQuery,
                                      client,
                                      episode_keys,
                                      None,
                                      must_exist=False),
                             gen.Task(Post.BatchQuery,
                                      client,
                                      post_keys,
                                      None,
                                      must_exist=False)]

    # Check that user has ability to access all source episodes and posts.
    ep_posts_list = []
    posts_iter = iter(posts)
    for (episode_id, photo_ids), episode in zip(ep_ph_ids_list, episodes):
      if episode is None:
        raise InvalidRequestError('Episode "%s" does not exist.' % episode_id)

      posts_list = []
      for photo_id in photo_ids:
        post = next(posts_iter)
        if post is None:
          raise InvalidRequestError('Photo "%s" does not exist or is not in episode "%s".' %
                                    (photo_id, episode_id))

        # Do not raise error if removing a photo that has already been unshared or removed.
        if action != 'remove':
          if post.IsUnshared():
            raise PermissionError('Cannot %s photo "%s", because it was unshared.' % (action, photo_id))

          if post.IsRemoved():
            raise PermissionError('Cannot %s photo "%s", because it was removed.' % (action, photo_id))

        posts_list.append(post)

      ep_posts_list.append((episode, posts_list))

    # Query for followers of all unique source viewpoints in parallel and in a batch.
    follower_keys = {episode.viewpoint_id: DBKey(user_id, episode.viewpoint_id) for episode in episodes}
    followers = yield gen.Task(Follower.BatchQuery, client, follower_keys.values(), None, must_exist=False)

    # Get set of all viewpoints that are accessible to this user.
    allowed_viewpoint_ids = set(follower.viewpoint_id for follower in followers
                                if follower is not None and follower.CanViewContent())

    # Check access permission to the source viewpoints.
    for episode in episodes:
      if episode.viewpoint_id not in allowed_viewpoint_ids:
        raise PermissionError('User %d does not have permission to %s episode "%s".' %
                              (user_id, action, episode.episode_id))

    raise gen.Return(ep_posts_list)

  @classmethod
  @gen.coroutine
  def _CheckCopySources(cls, action, client, user_id, source_ep_dicts):
    """Ensures that the sharer or saver has access to the source episodes and that the source
    photos are part of the source episodes. Caller is expected to check permission to add to
    the given viewpoint.

    Returns a list of the source episodes and posts in the form of (episode, posts) tuples.
    """
    # Gather list of (episode_id, photo_ids) tuples and check for duplicate posts.
    unique_keys = set()
    ep_ph_ids_list = []
    for ep_dict in source_ep_dicts:
      ph_ids = []
      for photo_id in ep_dict['photo_ids']:
        db_key = (ep_dict['new_episode_id'], photo_id)
        if db_key in unique_keys:
          raise InvalidRequestError('Photo "%s" cannot be %sd into episode "%s" more than once in same request.' %
                                    (photo_id, action, ep_dict['new_episode_id']))
        unique_keys.add(db_key)
        ph_ids.append(photo_id)

      ep_ph_ids_list.append((ep_dict['existing_episode_id'], ph_ids))

    ep_posts_list = yield ViewfinderOperation._CheckEpisodePostAccess(action, client, user_id, ep_ph_ids_list)
    raise gen.Return(ep_posts_list)

  @classmethod
  @gen.coroutine
  def _AllocateTargetEpisodeIds(self, client, user_id, device_id, target_viewpoint_id, source_ep_ids):
    """For each episode listed in "source_ep_ids", determines if a child episode already
    exists in the given viewpoint. If not, allocates a new episode id using the user's asset
    id allocator. The same timestamp used to create the source episode id is used to create
    the target episode id.

    Returns the list of target episodes ids, including both existing ids and allocated ids.
    """
    # First check whether each episode has already been shared/saved into the target viewpoint.
    tasks = []
    for source_ep_id in source_ep_ids:
      query_expr = ('episode.parent_ep_id={id}', {'id': source_ep_id})
      tasks.append(gen.Task(Episode.IndexQuery, client, query_expr, None))

    target_ep_ids = []
    allocate_ids_count = 0
    target_episodes_list = yield tasks
    for target_episodes in target_episodes_list:
      found_match = False
      for episode in target_episodes:
        if episode.viewpoint_id == target_viewpoint_id:
          target_ep_ids.append(episode.episode_id)
          found_match = True
          break

      # If no matching child episode, then need to allocate an episode id.
      if not found_match:
        target_ep_ids.append(None)
        allocate_ids_count += 1

    if allocate_ids_count > 0:
      # Allocate ids for any episodes which do not yet exist, and merge them into target_ep_ids.
      id = yield gen.Task(User.AllocateAssetIds, client, user_id, allocate_ids_count)
      for i, source_ep_id in enumerate(source_ep_ids):
        if target_ep_ids[i] is None:
          timestamp, _, _ = source_ep_id = Episode.DeconstructEpisodeId(source_ep_id)
          target_ep_ids[i] = Episode.ConstructEpisodeId(timestamp, device_id, id)
          id += 1

    raise gen.Return(target_ep_ids)

  @classmethod
  def _CreateCopyTargetDicts(cls, timestamp, user_id, target_viewpoint_id, source_ep_posts_list, target_ep_ids):
    """Creates list of dicts which will be used to create episodes that are the target of a
    share or save operation.
    """
    new_ep_dict_list = []
    for (source_episode, posts), target_ep_id in zip(source_ep_posts_list, target_ep_ids):
      new_ep_dict = {'episode_id': target_ep_id,
                     'parent_ep_id': source_episode.episode_id,
                     'user_id': user_id,
                     'viewpoint_id': target_viewpoint_id,
                     'timestamp': source_episode.timestamp,
                     'publish_timestamp': timestamp,
                     'location': source_episode.location,
                     'placemark': source_episode.placemark,
                     'photo_ids': [post.photo_id for post in posts]}
      new_ep_dict_list.append(new_ep_dict)

    return new_ep_dict_list

  @classmethod
  @gen.coroutine
  def _CheckCopyTargets(cls, action, client, user_id, viewpoint_id, target_ep_dicts):
    """Compiles a list of target episode and post ids that do not exist or are removed. These
    episodes and posts will not be copied as part of the operation.

    Returns the set of target episode and post ids that will be (re)created by the caller.
    """
    # Gather db keys for all target episodes and posts.
    episode_keys = []
    post_keys = []
    for ep_dict in target_ep_dicts:
      episode_keys.append(DBKey(ep_dict['episode_id'], None))
      for photo_id in ep_dict['photo_ids']:
        post_keys.append(DBKey(ep_dict['episode_id'], photo_id))

    # Query for all episodes and posts in parallel and in batches.
    episodes, posts = yield [gen.Task(Episode.BatchQuery,
                                      client,
                                      episode_keys,
                                      None,
                                      must_exist=False),
                             gen.Task(Post.BatchQuery,
                                      client,
                                      post_keys,
                                      None,
                                      must_exist=False)]

    # If a viewable post already exists, don't add it to the set to copy.
    new_ids = set()
    post_iter = iter(posts)
    for ep_dict, episode in zip(target_ep_dicts, episodes):
      if episode is None:
        # Add the episode id to the set to copy.
        new_ids.add(ep_dict['episode_id'])
      else:
        # Only owner user should get this far, since we check that new episode id contains the user's device id.
        assert episode.user_id == user_id, (episode, user_id)

        # Enforce sharing *tree* - no sharing acyclic graph allowed!
        if episode.parent_ep_id != ep_dict['parent_ep_id']:
          raise InvalidRequestError('Cannot %s to episode "%s". It was created from a different parent episode.' %
                                    (action, ep_dict['episode_id']))

        # Cannot share into episodes which are not in the target viewpoint.
        if episode.viewpoint_id != viewpoint_id:
          raise InvalidRequestError('Cannot %s to episode "%s". It is not in viewpoint "%s".' %
                                    (action, episode.episode_id, viewpoint_id))

      for photo_id in ep_dict['photo_ids']:
        post = next(post_iter)

        # If the post does not exist or is removed, add it to the new list. 
        if post is None or post.IsRemoved():
          new_ids.add(Post.ConstructPostId(ep_dict['episode_id'], photo_id))

    raise gen.Return(new_ids)

  @gen.coroutine
  def _CreateNewEpisodesAndPosts(self, new_ep_dicts, new_ids):
    """Creates new episodes and posts within those episodes based on a list returned by
    _CheckCopySources.

    If an episode or post id does not exist in "new_ids", it is not created. The "new_ids"
    set is created by _CheckCopyTargets.
    """
    tasks = []
    for new_ep_dict in deepcopy(new_ep_dicts):
      ep_id = new_ep_dict['episode_id']
      ph_ids = [ph_id for ph_id in new_ep_dict.pop('photo_ids')
                if Post.ConstructPostId(ep_id, ph_id) in new_ids]

      if ep_id in new_ids:
        tasks.append(gen.Task(Episode.CreateNew, self._client, **new_ep_dict))

      for ph_id in ph_ids:
        post = Post.CreateFromKeywords(episode_id=ep_id, photo_id=ph_id)
        post.labels.remove(Post.UNSHARED)
        post.labels.remove(Post.REMOVED)
        tasks.append(gen.Task(post.Update, self._client))

    yield tasks

  @classmethod
  @gen.coroutine
  def _GetAllContactsWithDedup(cls, client, user_id):
    """Query for all contacts and split into a dictionary of deduped contacts which is keyed by contact_id
    and a list of contacts that can be deleted because they're unnecessary.
    Returns: tuple of (retained_contacts_dict, contacts_to_delete_list)
    """
    contacts_to_delete = []
    contacts_to_retain = dict()
    # Query all contacts for this user.
    # Set query limit to be max that we expect multiplied by 2 to allow for some duplicates (there shouldn't be many).
    existing_contacts = yield gen.Task(Contact.RangeQuery,
                                       client,
                                       hash_key=user_id,
                                       range_desc=None,
                                       limit=Contact.MAX_CONTACTS_LIMIT * 2,
                                       col_names=['contact_id', 'labels', 'contact_source'],
                                       scan_forward=True)

    for existing_contact in existing_contacts:
      older_existing_contact = contacts_to_retain.pop(existing_contact.contact_id, None)
      if older_existing_contact is not None:
        contacts_to_delete.append(older_existing_contact)
      contacts_to_retain[existing_contact.contact_id] = existing_contact

    raise gen.Return((contacts_to_retain, contacts_to_delete))

  @classmethod
  def _GetRevivableFollowers(cls, followers):
    """Get subset of the given followers that have been removed but are still revivable."""
    return [follower.user_id for follower in followers
            if follower.IsRemoved() and not follower.IsUnrevivable()]

  @gen.coroutine
  def _ResolveContactIds(self, contact_dicts):
    """Examines each contact in "contact_dicts" (in the CONTACT_METADATA format). Returns a
    list of the same length containing the (True, user_id, webapp_dev_id) of the contact if
    it is already a Viewfinder user, or allocates new user and web device ids, and returns the
    tuple (False, user_id, webapp_dev_id).

    Raises an InvalidRequestError if any of the user ids do not correspond to real users.
    """
    # Get identity objects for all contacts for which no user_id is given.
    identity_keys = [DBKey(contact_dict['identity'], None)
                     for contact_dict in contact_dicts if 'user_id' not in contact_dict]

    identities = yield gen.Task(Identity.BatchQuery, self._client, identity_keys, None, must_exist=False)

    # Get user objects for all contacts with a user_id given, or if identity is already bound.
    user_keys = []
    ident_iter = iter(identities)
    for contact_dict in contact_dicts:
      if 'user_id' in contact_dict:
        user_keys.append(DBKey(contact_dict['user_id'], None))
      else:
        identity = next(ident_iter)
        if identity is not None and identity.user_id is not None:
          user_keys.append(DBKey(identity.user_id, None))

    users = yield gen.Task(User.BatchQuery, self._client, user_keys, None, must_exist=False)

    # Construct result tuples; if a user does not exist, allocate a user_id and webapp_dev_id.
    results = []
    ident_iter = iter(identities)
    user_iter = iter(users)
    for contact_dict in contact_dicts:
      if 'user_id' not in contact_dict:
        identity = next(ident_iter)
        if identity is None or identity.user_id is None:
          # User doesn't yet exist, so allocate new user and web device ids.
          user_id, webapp_dev_id = yield User.AllocateUserAndWebDeviceIds(self._client)
          results.append((False, user_id, webapp_dev_id))
          continue

      user = next(user_iter)
      if user is None:
        assert 'user_id' in contact_dict, contact_dict
        raise InvalidRequestError('A user with id %d cannot be found.' % contact_dict['user_id'])

      # User already exists.
      results.append((True, user.user_id, user.webapp_dev_id))

    raise gen.Return(results)

  @gen.coroutine
  def _ResolveContacts(self, contact_dicts, contact_ids, reason=None):
    """Creates a prospective user account for any contacts that are not yet Viewfinder users.
    The "contact_ids" list should have been previously obtained by the caller via a call to
    _ResolveContactIds, and items in it must correspond to "contact_dicts".
    If specified, the "reason" string is passed to the CreateProspective op. This describes what caused the user
    to be created (see db/analytics.py for payload details).
    """
    for contact_dict, (user_exists, user_id, webapp_dev_id) in zip(contact_dicts, contact_ids):
      if not user_exists:
        # Check if previous invocation of this operation already created the user.
        user = yield gen.Task(User.Query, self._client, user_id, None, must_exist=False)
        if user is None:
          # Create prospective user.
          request = {'user_id': user_id,
                     'webapp_dev_id': webapp_dev_id,
                     'identity_key': contact_dict['identity'],
                     'reason': reason}
          yield Operation.CreateNested(self._client, 'CreateProspectiveOperation.Execute', request)
