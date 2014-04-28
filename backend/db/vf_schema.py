# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""The Viewfinder schema definition.

The schema contains a set of tables. Each table is described by name,
key, a set of columns, and a list of versions.

The table name is the name used to access the database. The table key
is used to segment index terms by table. It, combined with the column
key, forms the prefix of each index term generated when a column value
is indexed.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

from schema import Schema, Table, IndexedTable, IndexTable, Column, HashKeyColumn, RangeKeyColumn, SetColumn, JSONColumn, LatLngColumn, PlacemarkColumn, CryptColumn
from indexers import Indexer, SecondaryIndexer, FullTextIndexer, EmailIndexer, LocationIndexer

ACCOUNTING = 'Accounting'
ACTIVITY = 'Activity'
ADMIN_PERMISSIONS = 'AdminPermissions'
ANALYTICS = "Analytics"
COMMENT = 'Comment'
CONTACT = 'Contact'
DEVICE = 'Device'
EPISODE = 'Episode'
FOLLOWED = 'Followed'
FOLLOWER = 'Follower'
FRIEND = 'Friend'
GUESS = 'Guess'
HEALTH_REPORT = 'HealthReport'
ID_ALLOCATOR = 'IdAllocator'
IDENTITY = 'Identity'
LOCK = 'Lock'
METRIC = 'Metric'
NOTIFICATION = 'Notification'
OPERATION = 'Operation'
PHOTO = 'Photo'
POST = 'Post'
SETTINGS = 'Settings'
SHORT_URL = 'ShortURL'
SUBSCRIPTION = 'Subscription'
USER = 'User'
USER_PHOTO = 'UserPhoto'
USER_POST = 'UserPost'
VIEWPOINT = 'Viewpoint'
INDEX = 'Index'

TEST_RENAME = 'TestRename'

SCHEMA = Schema([
    # The accounting table stores aggregated usage stats.
    # The hash and sort keys are strings consisting of 'prefix:<optional id>'
    #
    # Accounting categories:
    #   - Per viewpoint: hash_key='vs:<vp_id>'
    #     Aggregate sizes/counts per viewpoint, keyed by the viewpoint
    #     id. Sort keys fall into three categories:
    #     - owned by: 'ow:<user_id>' only found in default viewpoint.
    #     - shared by: 'sb:<user_id>' in shared viewpoint, sum of all photos
    #       in episodes owned by 'user_id'
    #     - visible to: 'vt' in shared viewpoint, sum of all photos. not keyed
    #       by user. a given user's "shared with" stats will be 'vt - sb:<user_id>',
    #       but we do not want to keep per-user shared-by stats.
    #   - Per user: hash_key='us:<user_id>'
    #     Aggregate sizes/counts per user, keyed by user id. Sort keys are:
    #     - owned by: 'ow' sum of all photos in default viewpoint
    #     - shared by: 'sb' sum of all photos in shared viewpoints and episodes owned by this user
    #     - visible to: 'vt' sum of all photos in shared viewpoint (includes 'sb'). to get the
    #       real count of photos shared with this user but not shared by him, compute 'vt - sb'
    #
    # 'op_ids' holds a list of previously-applied operation IDs. This is an attempt to
    # make increments idempotent with replays. The list is a comma-separated string of
    # operation ids (sometimes suffixed with a viewpoint ID), in the order in which they were
    # applied. We keep a maximum of Accounting._MAX_APPLIED_OP_IDS.
    #
    # Currently, all columns are used by each accounting category.
    Table(ACCOUNTING, 'at', read_units=100, write_units=10,
          columns=[HashKeyColumn('hash_key', 'hk', 'S'),
                   RangeKeyColumn('sort_key', 'sk', 'S'),
                   Column('num_photos', 'np', 'N'),
                   Column('tn_size', 'ts', 'N'),
                   Column('med_size', 'ms', 'N'),
                   Column('full_size', 'fs', 'N'),
                   Column('orig_size', 'os', 'N'),
                   Column('op_ids', 'oi', 'S')]),

    # Activities are associated with a viewpoint and contain a record of
    # all high-level operations which have modified the structure of the
    # viewpoint in some way. For more details, see activity.py. The
    # activity_id attribute is a composite of information gleaned from
    # current operation: (reverse timestamp, user_id, op_id). The content
    # of the activity is a JSON-encoded ACTIVITY structure, as defined in
    # json_schema.py. 'update_seq' is set to the value of the viewpoint's
    # 'update_seq' attribute after it was incremented during creation of
    # the activity.
    Table(ACTIVITY, 'ac', read_units=100, write_units=10,
          columns=[HashKeyColumn('viewpoint_id', 'vi', 'S'),
                   RangeKeyColumn('activity_id', 'ai', 'S'),
                   Column('user_id', 'ui', 'N', read_only=True),
                   Column('timestamp', 'ti', 'N', read_only=True),
                   Column('update_seq', 'us', 'N'),
                   Column('name', 'na', 'S', read_only=True),
                   Column('json', 'js', 'S', read_only=True)]),

    # Admin table. This table lists all users with access to admin and support functions.
    # Entries are created by the otp script, with 'rights' being a set of roles (eg: 'root' or 'support').
    # Admin users are not currently linked to viewfinder users.
    Table(ADMIN_PERMISSIONS, 'ad', read_units=10, write_units=10,
          columns=[HashKeyColumn('username', 'un', 'S'),
                   Column('rights', 'ri', 'SS')]),

    # Timestamped information for various entities. The entity hash key should be of the form: <type>:<id>.
    # eg: us:112 (for user with ID 112).
    # sort_key: base64 hex encoded timestamp + type
    # Type is a string representing the type of analytics entry. See db/analytics.py for details.
    # Payload is an optional payload attached to the entry. Its format depends on the type of entry.
    Table(ANALYTICS, 'an', read_units=10, write_units=10,
          columns=[HashKeyColumn('entity', 'et', 'S'),
                   RangeKeyColumn('sort_key', 'sk', 'S'),
                   Column('timestamp', 'ti', 'N'),
                   Column('type', 'tp', 'S'),
                   Column('payload', 'pl', 'S')]),

    # Key is composite of (viewpoint_id, comment_id), which sorts all
    # comments by ascending timestamp within each viewpoint. 'user_id'
    # is the user that created the comment. At this time, 'asset_id'
    # can be:
    #   1. Absent: The comment is not linked to any other asset.
    #   2. Comment id: The comment is a response to another comment.
    #   3. Photo id: The comment is a comment on a photo.
    #
    # 'timestamp' records the time that the comment was originally
    # created. 'message' is the actual comment text.
    IndexedTable(COMMENT, 'cm', read_units=200, write_units=20,
                 columns=[HashKeyColumn('viewpoint_id', 'vi', 'S'),
                          RangeKeyColumn('comment_id', 'ci', 'S'),
                          Column('user_id', 'ui', 'N', read_only=True),
                          Column('asset_id', 'ai', 'S', read_only=True),
                          Column('timestamp', 'ti', 'N'),
                          Column('message', 'me', 'S')]),

    # Key is composite of (user_id, sort_key)
    # sort_key: base64 hex encoded timestamp + contact_id
    # contact_id: contact_source + ':' + hash (base64 encoded) of CONTACT data: name, given_name, family_name,
    #     rank, and identities_properties columns.
    # contact_source: 'fb', 'gm', 'ip', or 'm'  (for, respectively, Facebook, GMail, iPhone, and Manual sources)
    # timestamp column should always match the timestamp encoded prefix of the sort_key.
    # identities: set of canonicalized identity strings: Email:<email-address>, Phone:<phone>, Facebook:<fb-graph-id>
    #   These reference identities in the IDENTITY table.  This column exists so that contacts can be queried by
    #   identity. Note: duplicates info that's contained in the identities_properties column.
    # identities_properties: json formatted list of identities each with an optional label such as 'mobile', 'work',
    #    etc...  This list preserves the order in which the identities were upload by (or fetched from) a
    #    contact source.  These identities may not be in canonicalized form, but it must be possible to canonicalize
    #    them.
    # labels: 'removed' indicates that the contact is in a removed state.  This surfaces the removed state of
    #   contacts to clients through invalidation notifications.  These contacts will be filtered out for down-level
    #   client queries.
    IndexedTable(CONTACT, 'co', read_units=50, write_units=120,
                 columns=[HashKeyColumn('user_id', 'ui', 'N'),
                          RangeKeyColumn('sort_key', 'sk', 'S'),
                          Column('timestamp', 'ti', 'N'),
                          Column('contact_id', 'ci', 'S', SecondaryIndexer(), read_only=True),
                          Column('contact_source', 'cs', 'S', read_only=True),
                          SetColumn('labels', 'lb', 'SS'),
                          SetColumn('identities', 'ids', 'SS', SecondaryIndexer(), read_only=True),
                          Column('name', 'na', 'S', read_only=True),
                          Column('given_name', 'gn', 'S', read_only=True),
                          Column('family_name', 'fn', 'S', read_only=True),
                          Column('rank', 'ra', 'N', read_only=True),
                          JSONColumn('identities_properties', 'ip', read_only=True)]),

    # Device information. Key is a composite of user id and a 32-bit
    # integer device id (allocated via the id-allocation table). Each
    # device is a source of photos. The device id comprises the first
    # 32 bits of the photo id. The last 32 bits are sequentially
    # allocated by the device (in the case of mobile), or via an
    # atomic increment of 'id_seq' (in the case of the web).
    #
    # 'last_access' and 'push_token' are set on device registration
    # and each time the application is launched (in the case of the
    # mobile app). 'push_token' is indexed to allow device lookups in
    # response to feedback from provider push-notification services.
    # 'alert_user_id' is a sparse column index, used to quickly find
    # all devices for a user that need to be alerted.
    #
    # Device ID of 0 is reserved to mean local to an individual device.
    #
    # Example Apple push token: "apns:oYJrenW5JsH42r1eevgq3HhC6bhXL3OP0SqHkOeo/58="
    IndexedTable(DEVICE, 'de', read_units=25, write_units=5,
                 columns=[HashKeyColumn('user_id', 'ui', 'N'),
                          RangeKeyColumn('device_id', 'di', 'N', SecondaryIndexer()),
                          Column('timestamp', 'ti', 'N'),
                          Column('name', 'na', 'S'),
                          Column('version', 've', 'S'),
                          Column('platform', 'pl', 'S'),
                          Column('os', 'os', 'S'),
                          Column('last_access', 'la', 'N'),
                          Column('alert_user_id', 'aui', 'N', SecondaryIndexer()),
                          Column('push_token', 'pt', 'S', SecondaryIndexer()),
                          Column('language', 'lg', 'S'),
                          Column('country', 'co', 'S')]),

    # Key is episode-id. Episodes are indexed for full-text search on
    # episode title and description, and lookup of all episodes for a user.
    # Due to a rename, the Episode table is called Event in the database.
    IndexedTable(EPISODE, 'ev', read_units=200, write_units=10, name_in_db="Event",
                 columns=[HashKeyColumn('episode_id', 'ei', 'S'),
                          Column('parent_ep_id', 'pa', 'S', SecondaryIndexer(), read_only=True),
                          Column('user_id', 'ui', 'N', SecondaryIndexer(), read_only=True),
                          Column('viewpoint_id', 'vi', 'S', SecondaryIndexer(), read_only=True),
                          Column('publish_timestamp', 'pu', 'N'),
                          Column('timestamp', 'cr', 'N'),
                          Column('title', 'ti', 'S'),
                          Column('description', 'de', 'S'),
                          LatLngColumn('location', 'lo'),
                          PlacemarkColumn('placemark', 'pl')]),

    # Sorts all viewpoints followed by a user in order of the date of
    # on which the last activity was added. Viewpoints updated on the
    # same day are in undefined order. Sort is in descending order, with
    # viewpoints most recently updated coming first. The query_followed
    # method returns results in this ordering. Note that paging may result
    # in missed followed records, as updates to a viewpoint may cause the
    # corresponding record to "jump ahead" in time past the current paging
    # bookmark. 'date_updated' is a timestamp truncated to a day boundary.
    # 'sort_key' is a concatenation of the 'date_updated' field and the
    # viewpoint id.
    IndexedTable(FOLLOWED, 'fd', read_units=200, write_units=10,
                 columns=[HashKeyColumn('user_id', 'ui', 'N'),
                          RangeKeyColumn('sort_key', 'sk', 'S'),
                          Column('date_updated', 'du', 'N'),
                          Column('viewpoint_id', 'vi', 'S', read_only=True)]),

    # Key is a composite of (user-id, viewpoint-id). The 'labels' set
    # specifies the features of the relation between the user and
    # viewpoint: ('admin', 'contribute'). 'adding_user_id' contains the id
    # of the user who added this follower, and 'timestamp' the time at which
    # the follower was added. 'viewed_seq' is the sequence number of the last
    # viewpoint update that has been 'read' by this follower. The last
    # viewpoint update is tracked by the 'update_seq' attribute on Viewpoint.
    IndexedTable(FOLLOWER, 'fo', read_units=400, write_units=10,
                 columns=[HashKeyColumn('user_id', 'ui', 'N'),
                          RangeKeyColumn('viewpoint_id', 'vi', 'S', SecondaryIndexer()),
                          Column('timestamp', 'ti', 'N'),
                          Column('adding_user_id', 'aui', 'N'),
                          SetColumn('labels', 'la', 'SS'),
                          Column('viewed_seq', 'vs', 'N')]),

    # Key is composite of user-id / friend-id. "colocated_shares" and
    # "total_shares" are decaying stats that track the number of photo
    # opportunities where sharing occurred. 'last_colocated' and
    # 'last_share' are timestamps for computing decay. Friend status is
    # one of {friend,blocked,muted}.
    Table(FRIEND, 'fr', read_units=50, write_units=10,
          columns=[HashKeyColumn('user_id', 'ui', 'N'),
                   RangeKeyColumn('friend_id', 'fi', 'N'),
                   Column('name', 'na', 'S'),
                   Column('nickname', 'nn', 'S'),
                   Column('colocated_shares', 'cs', 'N'),
                   Column('last_colocated', 'lc', 'N'),
                   Column('total_shares', 'ts', 'N'),
                   Column('last_share', 'ls', 'N'),
                   Column('status', 'st', 'S')]),

    # Tracks the number of incorrect attempts that have been made to guess some
    # secret, such as a password or an access code. 'guess_id' is of the form
    # <type>:<id>, where <type> is one of these:
    #
    #   url:<group-id> - Limits number of attempts that can be made to guess a
    #                    valid ShortURL within any particular 24-hour period.
    #
    #   pw:<user-id> - Limits number of attempts that can be made to guess a
    #                  particular user's password within any particular 24-hour
    #                  period.
    #
    #   em:<user-id> - Limits number of attempts that can be made to guess
    #                  access tokens e-mailed to a particular user within any
    #                  particular 24-hour period.
    #
    #   ph:<user-id> - Limits number of attempts that can be made to guess
    #                  access tokens sent in SMS messages to a user within any
    #                  particular 24-hour period.
    #
    # The 'guesses' field tracks the number of incorrect guesses that have been
    # made so far. The 'expires' field stores the time at which the guesses count
    # can be reset to 0.
    Table(GUESS, 'gu', read_units=50, write_units=10,
          columns=[HashKeyColumn('guess_id', 'gi', 'S'),
                   Column('expires', 'ex', 'N'),
                   Column('guesses', 'gu', 'N')]),

    # Key is a composite of (group_key, timestamp), where group_key is the
    # same key used to collect machine metrics in the metrics table.  The
    # intention is that for each metrics group_key, a single health report
    # will be generated summarizing problems across all machines in that group.
    #
    # Alerts and Warnings are string sets which describe any problems detected
    # from the metrics information.  If no problems are detected, this record
    # will be sparse.
    Table(HEALTH_REPORT, 'hr', read_units=10, write_units=5,
          columns=[HashKeyColumn('group_key', 'gk', 'S'),
                   RangeKeyColumn('timestamp', 'ts', 'N'),
                   SetColumn('alerts', 'as', 'SS'),
                   SetColumn('warnings', 'ws', 'SS')]),

    # Key is ID type (e.g. op-id, photo-id, user-id, episode-id).
    Table(ID_ALLOCATOR, 'ia', read_units=10, write_units=10,
          columns=[HashKeyColumn('id_type', 'it', 'S'),
                   Column('next_id', 'ni', 'N')]),

    # Key is identity. User-id is indexed to provide quick queries for the
    # list of identities associated with a viewfinder account. The token
    # allows access to external resources associated with the identity.
    # 'last_fetch' specifies the last time that the contacts were
    # fetched for this identity. 'authority' is one of ('Facebook', 'Google'
    # 'Viewfinder', etc.) and identifies the trusted authentication authority.
    #
    # The complete set of attributes (if any) returned when an
    # identity was authenticated is stored as a json-encoded dict in
    # 'json_attrs'. Some of these may be taken to populate the
    # demographic and informational attributes of the User table.
    #
    # The 'access_token' and 'refresh_token' fields store any tokens used to
    # access the authority, with 'expires' tracking the lifetime of the
    # token.
    #
    # The 'auth_throttle' field limits the number of auth email/sms messages
    # that can be sent within a certain period of time.
    IndexedTable(IDENTITY, 'id', read_units=50, write_units=10,
                 columns=[HashKeyColumn('key', 'ke', 'S'),
                          Column('user_id', 'ui', 'N', SecondaryIndexer()),
                          JSONColumn('json_attrs', 'ja'),
                          Column('last_fetch', 'lf', 'N'),
                          Column('authority', 'au', 'S'),
                          Column('access_token', 'at', 'S'),
                          Column('refresh_token', 'rt', 'S'),
                          Column('expires', 'ex', 'N'),
                          JSONColumn('auth_throttle', 'th'),

                          # TODO(Andy): Remove these attributes, as they are now deprecated.
                          Column('access_code', 'ac', 'S', SecondaryIndexer()),
                          Column('expire_code', 'xc', 'N'),
                          Column('token_guesses', 'tg', 'N'),
                          Column('token_guesses_time', 'gt', 'N')]),

    # A lock is acquired in order to control concurrent access to
    # a resource. The 'lock_id' is a composite of the type of the
    # resource and its unique id. The 'owner_id' is a string that
    # uniquely identifies the holder of the lock. 'resource_data'
    # is resource-specific information that is provided by the
    # owner and stored with the lock. The 'expiration' is the time
    # (UTC) at which the lock is assumed to have been abandoned by
    # the owner and can be taken over by another owner.
    #
    # 'acquire_failures' tracks the number of times other agents
    # tried to acquire the lock while it was held.
    Table(LOCK, 'lo', read_units=50, write_units=10,
          columns=[HashKeyColumn('lock_id', 'li', 'S'),
                   Column('owner_id', 'oi', 'S'),
                   Column('expiration', 'ex', 'N'),
                   Column('acquire_failures', 'af', 'N'),
                   Column('resource_data', 'rd', 'S')]),

    # Metrics represent a timestamped payload of performance metrics
    # from a single machine running viewfinder.  The metrics key is a
    # composite of (group_key, sort_key).  The payload column is a serialized
    # dictionary describing the performance metrics that were captured from
    # the machine.
    #
    # The group_key for a metric is intended to organize metrics by the way
    # they are queried.  For instance, a group key might contain all
    # metrics for all machines in an EC2 region, or a more specific division
    # than that.
    #
    # The sort_key is a composite of the timestamp and machine id - the
    # intention is that records will be queried by timestamp, while machine_id
    # is simply included in the key to differentiate records with the same
    # timestamp from different machines.
    IndexedTable(METRIC, 'mt', read_units=50, write_units=10,
                 columns=[HashKeyColumn('group_key', 'gk', 'S'),
                          RangeKeyColumn('sort_key', 'sk', 'S'),
                          Column('machine_id', 'mi', 'S', SecondaryIndexer()),
                          Column('timestamp', 'ts', 'N'),
                          Column('payload', 'p', 'S')]),

    # Notifications are messages to deliver to devices hosting the
    # viewfinder client, whether mobile, desktop, web application or
    # otherwise. Key is a composite of (user-id and allocated
    # notification id--taken from user's uu_id sequence). Other
    # fields record the name, id, and timestamp of the operation that
    # resulted in the notification, as well as the user and device
    # that started it. The badge attribute records the value of the
    # "push badge" on client devices at the time that notification
    # was recorded. The invalidate attribute is a JSON-encoded
    # INVALIDATE structure, as defined in json_schema.py.
    Table(NOTIFICATION, 'no', read_units=50, write_units=10,
          columns=[HashKeyColumn('user_id', 'ui', 'N'),
                   RangeKeyColumn('notification_id', 'ni', 'N'),
                   Column('name', 'na', 'S'),
                   Column('timestamp', 'ti', 'N'),
                   Column('sender_id', 'si', 'N'),
                   Column('sender_device_id', 'sd', 'N'),
                   Column('badge', 'ba', 'N'),
                   Column('invalidate', 'in', 'S'),
                   Column('op_id', 'oi', 'S'),
                   Column('viewpoint_id', 'vi', 'S'),
                   Column('update_seq', 'us', 'N'),
                   Column('viewed_seq', 'vs', 'N'),
                   Column('activity_id', 'ai', 'S')]),

    # Operations are write-ahead logs of mutating server
    # requests. These requests need to be persisted so that they can
    # be retried on server failure. They often involve multiple
    # queries / updates to different database tables and/or rows, so a
    # partially completed operation could leave the database in an
    # inconsistent state. Each operation must be idempotent, as
    # failing servers may cause retries. The actual operation is
    # stored JSON-encoded in 'json'. This is often the original HTTP
    # request, though in some cases, the JSON from the HTTP request
    # is augmented with additional information, such as pre-allocated
    # photo, user or device IDs.
    #
    # 'quarantine' indicates that if the operation fails, it
    # should not prevent further operations for the same user from
    # processing.
    #
    # 'checkpoint' stores progress information with the operation. If the
    # operation is restarted, it can use this information to skip over
    # steps it's already completed. The progress information is operation-
    # specific and is not used in any way by the operation framework itself.
    #
    # 'triggered_failpoints' is used for testing operation idempotency. It
    # contains the set of failpoints which have already been triggered for
    # this operation and need not be triggered again.
    Table(OPERATION, 'op', read_units=50, write_units=50,
          columns=[HashKeyColumn('user_id', 'ui', 'N'),
                   RangeKeyColumn('operation_id', 'oi', 'S'),
                   Column('device_id', 'di', 'N'),
                   Column('method', 'me', 'S'),
                   Column('json', 'js', 'S'),
                   Column('timestamp', 'ti', 'N'),
                   Column('attempts', 'at', 'N'),
                   Column('backoff', 'bo', 'N'),
                   Column('first_failure', 'ff', 'S'),
                   Column('last_failure', 'lf', 'S'),
                   Column('quarantine', 'sf', 'N'),
                   JSONColumn('checkpoint', 'cp'),
                   JSONColumn('triggered_failpoints', 'fa')]),

    # Key is photo-id. Photo id is composed of 32 bits of time in the
    # high 32 bits, then 32 bits of device id, then 32 bits of
    # monotonic photo id, unique to the device. The full 96 bits are
    # base-64 hex encoded into 128 bits. Photos can have a parent
    # photo-id, which refers back to an original photo if this is a
    # copy. Copies are made when filters are applied to photos. The
    # client_data string is a JSON-encoded dict of opaque
    # client-supplied key-value pairs.
    #
    # The 'share_seq_no' attribute is incremented every time the shares
    # for a photo are modified. It provides for efficient queries from
    # clients meant to determine the list of friends with viewing
    # privileges
    #
    # Sizes for tn, med, full, orig are file sizes in bytes for thumnail,
    # medium, full and original images respectively.
    #
    # The 'new_assets' attribute is temporary and there to support rename
    # of image asset files from underscore to period suffixes. It contains
    # the value 'copied' if the asset files have been duplicated and
    # 'deleted' if the original asset files have been verified as copied
    # and removed.
    # TODO(spencer): remove this once we have completely migrated the photo
    # data.
    #
    # 'client_data' is deprecated; use USER_PHOTO instead.
    IndexedTable(PHOTO, 'ph', read_units=400, write_units=25,
                 columns=[HashKeyColumn('photo_id', 'pi', 'S'),
                          Column('parent_id', 'pa', 'S', SecondaryIndexer(), read_only=True),
                          Column('episode_id', 'ei', 'S', read_only=True),
                          Column('user_id', 'ui', 'N', read_only=True),
                          Column('aspect_ratio', 'ar', 'N'),
                          Column('content_type', 'ct', 'S', read_only=True),
                          Column('timestamp', 'ti', 'N'),
                          Column('tn_md5', 'tm', 'S'),
                          Column('med_md5', 'mm', 'S'),
                          Column('orig_md5', 'om', 'S', SecondaryIndexer()),
                          Column('full_md5', 'fm', 'S', SecondaryIndexer()),
                          Column('tn_size', 'ts', 'N'),
                          Column('med_size', 'ms', 'N'),
                          Column('full_size', 'fs', 'N'),
                          Column('orig_size', 'os', 'N'),
                          LatLngColumn('location', 'lo'),
                          PlacemarkColumn('placemark', 'pl'),
                          Column('caption', 'ca', 'S',
                                 FullTextIndexer(metaphone=Indexer.Option.YES)),
                          Column('link', 'li', 'S'),
                          Column('thumbnail_data', 'da', 'S'),
                          Column('share_seq', 'ss', 'N'),
                          JSONColumn('client_data', 'cd'), # deprecated
                          Column('new_assets', 'na', 'S')]),

    # Key is composite of (episode-id, photo_id). When photos are
    # posted/reposted to episodes, a post relation is created. This
    # allows the same photo to be included in many episodes. The
    # 'labels' attribute associates a set of properties with the
    # post.
    IndexedTable(POST, 'po', read_units=200, write_units=25,
                 columns=[HashKeyColumn('episode_id', 'ei', 'S'),
                          RangeKeyColumn('photo_id', 'sk', 'S'),
                          SetColumn('labels', 'la', 'SS')]),

    # Key is composite of (settings_id, group_name). 'settings_id' is the
    # id of the entity to which the settings apply. For example, user account
    # settings have ids like 'us:<user_id>'. 'group_name' can be used if
    # a particular entity has large numbers of settings that need to be
    # sub-grouped.
    #
    # All other columns are a union of all columns defined by all the groups
    # stored in the table. The Settings class has support for only exposing
    # columns that apply to a particular group, in order to avoid accidental
    # use of a column belonging to another settings group.
    Table(SETTINGS, 'se', read_units=100, write_units=10,
          columns=[HashKeyColumn('settings_id', 'si', 'S'),
                   RangeKeyColumn('group_name', 'gn', 'S'),

                   # User account group settings.
                   Column('user_id', 'ui', 'N'),
                   Column('email_alerts', 'ea', 'S'),
                   Column('sms_alerts', 'sa', 'S'),
                   Column('push_alerts', 'pa', 'S'),
                   Column('marketing', 'mk', 'S'),
                   Column('sms_count', 'sc', 'N'),
                   SetColumn('storage_options', 'so', 'SS')]),

    # Key is composite of (group_id, random_key). 'group_id' partitions the URL
    # space into groups, so that URL's generated for one group have no overlap
    # with those for another group. The group id will be appended as the URL
    # path, so it may contain '/' characters, and should be URL safe. The
    # 'timestamp' column tracks the time at which the ShortURL was created.
    #
    # The 'json' column contains arbitrary named arguments that are associated
    # with the short URL and are pased to the request handler when the short
    # URL is used. The 'expires' field bounds the time during which the URL
    # can be used.
    Table(SHORT_URL, 'su', read_units=25, write_units=5,
          columns=[HashKeyColumn('group_id', 'gi', 'S'),
                   RangeKeyColumn('random_key', 'rk', 'S'),
                   Column('timestamp', 'ti', 'N'),
                   Column('expires', 'ex', 'N'),
                   JSONColumn('json', 'js')]),

    # The subscription table contains a user's current
    # subscription(s).  A subscription is any time-limited
    # modification to a user's privileges, such as increased storage
    # quota.
    #
    # This table contains a log of all transactions that have affected
    # a user's subscriptions.  In most cases only the most recent
    # transaction for a given subscription_id is relevant - it is the
    # most recent renewal.
    #
    # "product_type" is the type of subscription, such as "storage".
    # Quantity is a interpreted based on the product_type; for the
    # "storage" product it is a number of GB.  "payment_type"
    # indicates how the subscription was paid for (e.g.  "itunes" or
    # "referral_bonus").  The contents of "extra_info" and
    # "renewal_data" depend on the payment type.  "extra_info" is a
    # dict of additional information related to the transaction, and
    # "renewal_data" is an opaque blob that is used to renew a subscription
    # when it expires.
    Table(SUBSCRIPTION, 'su', read_units=10, write_units=5,
          columns=[HashKeyColumn('user_id', 'ui', 'N'),
                   RangeKeyColumn('transaction_id', 'tr', 'S'),
                   Column('subscription_id', 'su', 'S', read_only=True),
                   # timestamps should be read-only too, once we fix
                   # problems with read-only floats.
                   Column('timestamp', 'ti', 'N'),
                   Column('expiration_ts', 'ex', 'N'),
                   Column('product_type', 'pr', 'S', read_only=True),
                   Column('quantity', 'qu', 'N'),
                   Column('payment_type', 'pt', 'S', read_only=True),
                   JSONColumn('extra_info', 'ei'),
                   Column('renewal_data', 'pd', 'S', read_only=True)]),

    # Key is user id. 'webapp_dev_id' is assigned on creation, and
    # serves as a unique ID with which to formulate asset IDs in
    # conjunction with the 'asset_id_seq' attribute. This provides a
    # monotonically increasing sequence of episode/viewpoint/photo ids
    # for uploads via the web application. The 'uu_id_seq' provides a
    # similar increasing sequence of user update sequence numbers for
    # a user.
    #
    # Facebook email is kept separately in an effort to maximize
    # deliverability of Viewfinder invitations to Facebook contacts.
    # The from: header of those emails must be from the email address
    # registered for the Facebook user if incoming to
    # <username>@facebook.com.
    #
    # 'last_notification' is the most recent notification id which has
    # been queried by any of the user's devices. This is the watermark
    # used to supply the badge for push notifications. 'badge' is set
    # appropriately in response to notifications generated by account
    # activity.
    #
    # The 'merged_with' column specifies the sink user account with
    # which this user was merged. If 'merged_with' is set, this user
    # account is invalid and should not be used. If at all possible,
    # the request intended for this user should be re-routed to the
    # 'merged_with' user.
    #
    # The 'signing_key' column is a Keyczar signing keyset used when
    # it is desirable to sign a payload with a key that is specific to
    # one particular user. The contents of the column are encrypted
    # with the service-wide db crypt keyset.
    #
    # The 'pwd_hash' and 'salt' columns are used to securely generate
    # and store an iterative SHA1 hash of the user's password + salt. 
    #
    # For user index, range key column is a string-version of user ID.
    IndexedTable(USER, 'us', read_units=50, write_units=50,
                 columns=[HashKeyColumn('user_id', 'ui', 'N'),
                          Column('private_vp_id', 'pvi', 'S'),
                          Column('webapp_dev_id', 'wdi', 'N'),
                          Column('asset_id_seq', 'ais', 'N'),
                          Column('uu_id_seq', 'uis', 'N'),
                          Column('given_name', 'fi', 'S', FullTextIndexer()),
                          Column('family_name', 'la', 'S', FullTextIndexer()),
                          Column('name', 'na', 'S', FullTextIndexer()),
                          Column('email', 'em', 'S', EmailIndexer()),
                          Column('facebook_email', 'fe', 'S'),
                          LatLngColumn('location', 'lo', LocationIndexer()),
                          Column('gender', 'ge', 'S'),
                          Column('locale', 'lc', 'S'),
                          Column('link', 'li', 'S'),
                          Column('phone', 'ph', 'S'),
                          Column('picture', 'pi', 'S'),
                          Column('timezone', 'ti', 'N'),
                          Column('last_notification', 'ln', 'N'),
                          Column('badge', 'ba', 'N'),
                          Column('merged_with', 'mw', 'N'),
                          SetColumn('labels', 'lb', 'SS'),
                          CryptColumn('signing_key', 'sk'),
                          CryptColumn('pwd_hash', 'pwd'),
                          CryptColumn('salt', 'slt'),

                          # Deprecated (to be removed).
                          Column('beta_status', 'bs', 'S')]),

    # The USER_PHOTO is associated with a PHOTO object, and
    # represents user-specific information about the photo.
    # Specifically, this includes mappings between the photo and a
    # device's native asset library.  Normally only the user/device
    # who originated the photo will have a USER_PHOTO entry for it,
    # but it is possible for other users to create USER_PHOTOS if
    # they export a photo to their camera roll.
    IndexedTable(USER_PHOTO, 'up', read_units=400, write_units=10,
                 columns=[HashKeyColumn('user_id', 'di', 'N'),
                          RangeKeyColumn('photo_id', 'pi', 'S'),
                          SetColumn('asset_keys', 'ak', 'SS')]),

    # The USER_POST is associated with a POST object, and represents
    # user-specific override of information in the POST. 'timestamp'
    # records the creation time of the record, and 'labels' contains
    # a set of values which describes the customizations. For example,
    # the 'removed' label indicates that the post should not be shown
    # in the user's personal collection.
    #
    # Rows in the USER_POST table are only created if the user wants
    # to customize the viewpoint in some way. In the absence of a
    # row, default values are assumed.
    IndexedTable(USER_POST, 'uo', read_units=400, write_units=10,
                 columns=[HashKeyColumn('user_id', 'ui', 'N'),
                          RangeKeyColumn('post_id', 'pi', 'S'),
                          Column('timestamp', 'ti', 'N'),
                          SetColumn('labels', 'la', 'SS')]),

    # Key is viewpoint-id. Viewpoints are a collection of episodes.
    # Viewpoint title and description are indexed for full-text
    # search. The viewpoint name, sort of like a twitter
    # handler, is also indexed. 'type' is one of:
    #   ('default', 'event', 'thematic')
    #
    # The 'update_seq' is incremented each time a viewpoint asset
    # is added, removed, or updated. Using this with the 'viewed_seq'
    # attribute on Follower, clients can easily determine if there
    # is any "unread" content in the viewpoint. Note that updates to
    # user-specific content on Follower does not trigger the increment
    # of this value. 'last_updated' is set to the creation timestamp of
    # the latest activity that was added to this viewpoint.
    #
    # The 'cover_photo' column is a JSON-encoded dict of photo_id and
    # episode_id which indicates which photo should be used as the cover
    # photo for the viewpoint.  An absent column or None value for this indicates
    # that it's explicitly not available (no visible photos in the viewpoint).
    # Default viewpoints will not have this column set.
    IndexedTable(VIEWPOINT, 'vp', read_units=400, write_units=10,
                 columns=[HashKeyColumn('viewpoint_id', 'vi', 'S'),
                          Column('user_id', 'ui', 'N', SecondaryIndexer(), read_only=True),
                          Column('timestamp', 'ts', 'N', read_only=True),
                          Column('title', 'ti', 'S',
                                 FullTextIndexer(metaphone=Indexer.Option.YES)),
                          Column('description', 'de', 'S',
                                 FullTextIndexer(metaphone=Indexer.Option.YES)),
                          Column('last_updated', 'lu', 'N'),
                          Column('name', 'na', 'S', SecondaryIndexer()),
                          Column('type', 'ty', 'S', read_only=True),
                          Column('update_seq', 'us', 'N'),
                          JSONColumn('cover_photo', 'cp')]),

    # The index table for all indexed terms. Maps from a string to a
    # string for greatest flexibility. This requires that the various
    # database objects convert from a string value if the doc-id
    # actually does represent a number, such as the user-id in some of
    # the indexed tables in this schema.
    IndexTable(INDEX, 'S', 'S', read_units=200, write_units=50),

    # For the dynamodb_client_test.
    Table(TEST_RENAME, 'test', read_units=10, write_units=5, name_in_db="Test",
          columns=[HashKeyColumn('test_hk', 'thk', 'S'),
                   RangeKeyColumn('test_rk', 'trk', 'N'),
                   Column('attr0', 'a0', 'N'),
                   Column('attr1', 'a1', 'N'),
                   Column('attr2', 'a2', 'S'),
                   Column('attr3', 'a3', 'NS'),
                   Column('attr4', 'a4', 'SS')]),
    ])
