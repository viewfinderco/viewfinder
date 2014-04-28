# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Schema definition.

The first set of classes in this file handle the underlying storage
for a single column of a datastore object. The base class for this,
_Value, defines the interface. There are three subclasses:
_SingleValue, which handles one piece of data, whatever the type
(e.g. an integer, floating point, latitude/longitude pair, string,
etc.); _SetValue, which handles a set of _SingleValue
data; and _KeyValue, which hold an immutable key value.

_SetValue objects are used to represent one or more similar
items for an object. For example, a user object might contain one
email string for each verified identity.

This module provides the following utilities for packing / unpacking
data between a database-friendly ASCII data and structured named tuples.

  PackLocation: Location from named tuple to DB data
  UnpackLocation: from DB data to Location named tuple
  PackPlacmark: Placemark from named tuple to DB data
  UnpackPlacemark: from DB data to Placemark named tuple

This module provides the following external classes:

  Column: a single value column definition
  SetColumn: a set of values column definition
  Table: Contains one or more columns
  IndexedTable: Variant of Table which maintains secondary indexes
  IndexTable: Variant of Table which stores index info
  Schema: Contains one or more tables
  SchemaException: exception class for schema operations
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import json
import logging
import struct

from collections import namedtuple
from functools import partial
from tornado import options
from viewfinder.backend.base import base64hex, secrets, util
from viewfinder.backend.db import db_client, indexers

options.define('delete_vestigial', default=False, help='deletes vestigial tables')
options.define('verify_provisioning', default=True,
               help='abort if provisioned capacity does not match schema values')

Location = namedtuple('Location', ['latitude', 'longitude', 'accuracy'])

Placemark = namedtuple('Placemark', ['iso_country_code', 'country', 'state', 'locality',
                                     'sublocality', 'thoroughfare', 'subthoroughfare'])


def PackLocation(location):
  """Converts 'location' named tuple into a packed, base64-hex-encoded
  string representation for storage in DynamoDB.
  """
  packed = struct.pack('>ddd', *[float(x) for x in location])
  return base64hex.B64HexEncode(packed)

def UnpackLocation(value):
  """Converts from a packed, base64-hex-encoded representation of
  latitude, longitude and accuracy into a Location namedtuple.
  """
  packed = base64hex.B64HexDecode(value)
  latitude, longitude, accuracy = struct.unpack('>ddd', packed)
  return Location(latitude=latitude, longitude=longitude, accuracy=accuracy)


def PackPlacemark(placemark):
  """Converts 'placemark' named tuple into a packed,
  base64-hex-encoded, comma-separated representation for storage in
  DynamoDB.
  """
  return ','.join([base64hex.B64HexEncode(x.encode('utf-8'), padding=False) for x in placemark])

def UnpackPlacemark(value):
  """Converts from a comma-separated, base64-hex-encoded
  representation of hierarchical place names into 'Placemark' named
  tuple with an utf-8 encoded place names.
  """
  pm_values = []
  for x in value.split(','):
    try:
      # TODO(spencer): the rstrip() below is necessary as data in the
      # index has already been encoded with a bug in the base64 padding
      # We need to rebuild the index before reverting this.
      decoded_x = base64hex.B64HexDecode(x.rstrip('='), padding=False).decode('utf-8')
    except:
      decoded_x = ''
    pm_values.append(decoded_x)
  return Placemark(*pm_values)


class SchemaException(Exception):
  pass


class _Value(object):
  """Holds a column value. Each column type decides how to store its
  in-memory representation. Some column types are like _PlacemarkValue,
  where the raw db value is stored in memory as a more useful Python
  object. Other column types are like _JSONValue -- the raw db value
  is stored in memory and converted to a useful Python object on demand.
  """
  __slots__ = ['col_def', '_modified', '_value']

  def __init__(self, col_def):
    self.col_def = col_def
    self._modified = False
    self._value = None

  def IsModified(self):
    return self._modified

  def SetModified(self, modified):
    self._modified = modified

  def Get(self, asdict=False):
    """Returns the value of the column in a format that is convenient
    for use in Python. If 'asdict' is true, then convert to a Python
    dict if this column type supports it.
    """
    raise NotImplementedError()

  def Load(self, value):
    """Loads the value of the column from the format that is stored in the
    database. Sets the IsModified bit to false.
    """
    raise NotImplementedError()

  def Set(self, value):
    """Updates the value of the column with any type that can be converted
    into the column type. Sets the IsModified bit to true if the value of
    the column actually changes.
    """
    raise NotImplementedError()

  def Del(self):
    raise NotImplementedError()

  def Update(self):
    raise NotImplementedError()

  def OnUpdate(self):
    """Called on completion of an update."""
    self.SetModified(False)

  def IndexTerms(self):
    """Returns an index term dict in conjunction with PUT. If the term
    dict is empty, returns an empty term dict. In either case, the
    previous set of index terms is queried and the difference between
    the old and new sets is used to delete or add this object's key to
    the term posting lists.
    """
    assert self.col_def.indexer
    try:
      if self.Get():
        index_terms = self.col_def.indexer.Index(self.col_def, self.Get())
      else:
        index_terms = {}
    except:
      logging.exception('generation of index terms for %s' % repr(self.Get()))
      index_terms = {}

    return db_client.UpdateAttr(value=index_terms or None, action='PUT')

  def _CheckType(self, value):
    """Ensure that "value" has a type that matches the type of the column.
    """
    def _CheckSingleValue(single_value):
      assert single_value != '', value
      if self.col_def.value_type in ['S', 'SS']:
        is_expected_type = type(single_value) in [str, unicode]
      else:
        assert self.col_def.value_type in ['N', 'NS'], self.col_def
        is_expected_type = type(single_value) in [int, long, float]

      assert is_expected_type, \
             (self.col_def.table.name, self.col_def.value_type, self.col_def.name, value)

    if value is not None:
      if self.col_def.value_type in ['SS', 'NS']:
        [_CheckSingleValue(v) for v in value if v is not None]
      else:
        _CheckSingleValue(value)


class _SingleValue(_Value):
  """Holds a column with a single value (such as a string, a timestamp, etc.).
  """
  def Get(self, asdict=False):
    """Returns the value in the raw db format by default."""
    return self._value

  def Load(self, value):
    """Stores the raw db value by default."""
    self._CheckType(value)
    self._value = value

  def Set(self, value):
    """Stores the raw db value by default."""
    assert value != '', 'DynamoDB does not support setting attributes to the empty string'
    if value != self._value:
      assert not self.col_def.read_only or self._value is None, \
             'cannot modify read-only column "%s": %s=>%s' % (self.col_def.name, self._value, repr(value))
      self._CheckType(value)
      self.SetModified(True)
      self._value = value

  def Update(self):
    """Returns PUT and the new value if modified. If new value is
    None, returns DELETE.
    """
    assert self.IsModified()
    if self._value is not None:
      return db_client.UpdateAttr(value=self._value, action='PUT')
    else:
      return db_client.UpdateAttr(value=None, action='DELETE')


class _LatLngValue(_Value):
  """Subclass of _Value that holds latitude, longitude and an accuracy
  measure, all double-precision floating point values. They are
  stored together as a base64hex-encoded struct-packed string for
  storage, but are available as a Location namedtuple.

  This value may be set via either Set(Location(latitude, longitude, accuracy)),
  Set({'latitude': <latitude>, 'longitude': <longitude>, 'accuracy': <accuracy>}),
  or Set(packed-b64hex-encoded-string).
  """
  def Get(self, asdict=False):
    """Gets the value as a Location or dict object."""
    if asdict:
      return self._value._asdict()
    else:
      return self._value

  def Load(self, value):
    """Stores the raw db str as a Location object in memory."""
    assert isinstance(value, (str, unicode)), value
    self._value = UnpackLocation(value)

  def Set(self, value):
    """Converts 'value' to a Location and store."""
    if value is None:
      location = None
    elif isinstance(value, dict):
      location = Location(**value)
    elif isinstance(value, (str, unicode)):
      location = UnpackLocation(value)
    else:
      assert isinstance(value, Location), value
      location = value

    if location != self._value:
      self.SetModified(True)
      self._value = location

  def Update(self):
    """Returns PUT and the new value if modified. If new value is
    None, returns DELETE.
    """
    assert self.IsModified()
    if self._value is not None:
      return db_client.UpdateAttr(value=PackLocation(self._value), action='PUT')
    else:
      return db_client.UpdateAttr(value=None, action='DELETE')


class _PlacemarkValue(_Value):
  """Subclass of _Value that holds hierarchical placenames. They are stored
  together in the datastore as a url-encoded, comma-separated string, but are
  available in python as a Placemark namedtuple.

  This value may be set via either Set(Placemark), or
  Set({'iso_country_code', 'country': <country>, 'state': <state>,
  'locality': <locality>, 'sublocality': <sublocality>,
  'thoroughfare': <thoroughfare>, 'subthoroughfare':
  <subthoroughfare>}), or Set(<url-encoded, comma-separated string>).
  """
  def Get(self, asdict=False):
    """Gets the value as a Placemark or dict object."""
    if asdict:
      # Cannot return empty strings for missing placemark fields as
      # JSON validator doesn't allow empty strings.
      return dict([(k, v) for k, v in self._value._asdict().items() \
                     if v is not None and v != ''])
    else:
      return self._value

  def Load(self, value):
    """Stores the raw db str as a Placemark object in memory."""
    assert isinstance(value, (str, unicode)), value
    self._value = UnpackPlacemark(value)

  def Set(self, value):
    """Converts 'value' to a Placemark and store."""
    if value is None:
      placemark = None
    elif isinstance(value, dict):
      placemark = Placemark(value.get('iso_country_code', ''), value.get('country', ''),
                            value.get('state', ''), value.get('locality', ''),
                            value.get('sublocality', ''), value.get('thoroughfare', ''),
                            value.get('subthoroughfare', ''))
    elif isinstance(value, (str, unicode)):
      placemark = UnpackPlacemark(value)
    else:
      assert isinstance(value, Placemark), value
      placemark = value

    if placemark != self._value:
      self.SetModified(True)
      self._value = placemark

  def Update(self):
    """Returns PUT and the new value if modified. If new value is
    None, returns DELETE.
    """
    assert self.IsModified()
    if self._value is not None:
      return db_client.UpdateAttr(value=PackPlacemark(self._value), action='PUT')
    else:
      return db_client.UpdateAttr(value=None, action='DELETE')


class _JSONValue(_Value):
  """Subclass of _Value that holds a python data structure, which is
  stored as a JSON-encoded string.
  """
  def Get(self, asdict=False):
    """Returns the JSON-encoded string converted to a Python data type."""
    if self._value:
      return json.loads(self._value)
    else:
      return None

  def Load(self, value):
    """Stores the raw string value loaded from the db."""
    assert isinstance(value, (str, unicode)), value
    self._value = value

  def Set(self, value):
    """Converts 'value' to a JSON-encoded string before storing it."""
    value = util.ToCanonicalJSON(value)
    if value != self._value:
      self.SetModified(True)
      self._value = value

  def Update(self):
    assert self.IsModified()
    if self._value is not None:
      return db_client.UpdateAttr(value=self._value, action='PUT')
    else:
      return db_client.UpdateAttr(value=None, action='DELETE')


class _DelayedCrypt(object):
  """This class delays the decryption of an encrypted value until the class is invoked. This
  level of indirection ensures that the caller must take explicit action in order to decrypt
  a value. This helps to prevent accidental logging or use of the plaintext.
  """
  def __init__(self, encrypted_value):
    self._encrypted_value = encrypted_value

  def Decrypt(self):
    """Returns the decrypted value."""
    crypter = _CryptValue._GetCrypter()
    return json.loads(crypter.Decrypt(self._encrypted_value))

  def __eq__(self, other):
    """Returns true if self._encrypted_value is equal to the other's _encrypted_value."""
    if isinstance(other, _DelayedCrypt):
      return self._encrypted_value == other._encrypted_value
    return NotImplemented

  def __ne__(self, other):
    """Returns true if self._encrypted_value is not equal to the other's _encrypted_value."""
    if isinstance(other, _DelayedCrypt):
      return self._encrypted_value != other._encrypted_value
    return NotImplemented


class _CryptValue(_JSONValue):
  """Subclass of _Value that holds a python data structure, which is stored as a JSON-encoded
  string that has been encrypted with the service-wide db crypt key.
  """
  @classmethod
  def _GetCrypter(cls):
    if not hasattr(cls, '_crypter'):
      cls._crypter = secrets.GetCrypter('db_crypt')
    return cls._crypter

  def Get(self, asdict=False):
    """Gets the encrypted value as an instance of _DelayedCrypt. This instance's Decrypt method
    must be invoked in order to extract the unencrypted value. See the docs for _DelayedCrypt
    for details.
    """
    if self._value is not None:
      # Return JSON-friendly format when _asdict() is used. The default JSONEncoder does not
      # handle anything other than the basic Python types. Note that in this case, decrypting
      # the value via invocation is not possible, but it is useful for getting an object as a
      # dict, and then serializing or copying it elsewhere.
      if asdict:
        return {'__crypt__': self._value}

      return _DelayedCrypt(self._value)
    else:
      return None

  def Set(self, value):
    """Converts 'value' to a JSON-encoded string and encrypts it before storing it."""
    if value is None:
      encrypted_value = None
    elif isinstance(value, _DelayedCrypt):
      encrypted_value = value._encrypted_value
    elif isinstance(value, dict) and '__crypt__' in value:
      encrypted_value = value['__crypt__']
    else:
      crypter = _CryptValue._GetCrypter()
      encrypted_value = crypter.Encrypt(json.dumps(value))

    if self._value != encrypted_value:
      self.SetModified(True)
      self._value = encrypted_value


class _LayeredSet(frozenset):
  """A special frozenset subclass which handles deletions and
  additions without necessarily knowing about the contents of the
  canonical set (as it exists at the current moment in the
  datastore). This is useful for describing changes to a set of
  values in the datastore without requiring the contents be
  queried. It redefines add, clear, discard & remove by augmenting
  additional, internal set() objects to track additions and
  deletions. These are then used to update the datastore as
  incremental changes.

  Once a value has been removed, it cannot then be added and vice-
  versa. Values which have been added or removed are transient and
  have no effect on tests for whether an element is 'in' the set, on
  set equality, or on set operations. These types of set operations
  are valid only with the results of set values queried from the
  datastore. clear() adds all elements which were queried (ones in the
  underlying frozenset) to the deleted set. Any elements previously
  added to additions are discarded.

  The return values of various methods must be judiciously
  interpreted. Asking if 'x in _LayeredSet' may yield an answer only
  in relation to imperfect knowledge of the canonical set.
  """
  def __init__(self, s=[]):
    super(_LayeredSet, self).__init__(s)
    self.additions = set()
    self.deletions = set()

  def __repr__(self):
    return '%s +%s -%s' % (super(_LayeredSet, self).__repr__(),
                           self.additions.__repr__(),
                           self.deletions.__repr__())

  def add(self, elem):
    assert not self.deletions
    assert elem != ''
    if elem not in self:
      self.additions.add(elem)

  def clear(self):
    self.deletions = set(self)
    self.additions.clear()

  def discard(self, elem):
    self.remove(elem)

  def remove(self, elem):
    assert not self.additions
    self.deletions.add(elem)

  def combine(self):
    """Return a set that adds the additions and removes the deletions."""
    return self.additions.union(self).difference(self.deletions)

class _SetValue(_Value):
  """Holds a set of values using a LayeredSet to keep track of
  incremental additions and deletions.
  """
  def __init__(self, col_def):
    super(_SetValue, self).__init__(col_def)
    self._value = _LayeredSet()

  def IsModified(self):
    """True if _modified or if additions or deletions are not empty."""
    return self._modified or self._value.additions or self._value.deletions

  def Get(self, asdict=False):
    """Returns the partial set."""
    if asdict:
      return list(self._value)
    else:
      return self._value

  def Load(self, value):
    """Stores the raw set value as a LayeredSet."""
    assert value is None or isinstance(value, (list, tuple, set, frozenset)), type(value)
    if value is None:
      self._value = _LayeredSet()
    else:
      self._value = _LayeredSet(value)

  def Set(self, value):
    """Sets the contents of the entire set. This sets a flag which
    indicates that the DynamoDB update should use a PUT action to
    replace the previous contents of the set.
    """
    self.SetModified(True)
    self.Load(value)

  def Update(self):
    """Returns an action {ADD, DELETE, PUT} and the set of values for
    an update depending on the state of the layered set. If the set
    was assigned directly, use PUT. If there are set additions, use
    ADD; otherwise DELETE.
    """
    if self._modified:
      if self._value.additions:
        value = list(self._value.union(self._value.additions))
      else:
        value = list(self._value.difference(self._value.deletions))

      # DynamoDB does not support PUT of empty set, so instead DELETE the attribute entirely.
      if not value:
        return db_client.UpdateAttr(None, action='DELETE')

      return db_client.UpdateAttr(value=value, action='PUT')
    else:
      if self._value.additions:
        return db_client.UpdateAttr(value=list(self._value.additions), action='ADD')
      elif self._value.deletions:
        return db_client.UpdateAttr(value=list(self._value.deletions), action='DELETE')
      else:
        assert False, 'Update called with unmodified set'

  def OnUpdate(self):
    """Called on completion of an update."""
    self._modified = False
    new_set = self._value.combine()
    self._value = _LayeredSet(new_set)

  def IndexTerms(self):
    """Returns the set of index terms in conjunction with the action,
    which is one of {PUT, ADD, DELETE}. Index terms which are meant to
    replace the former set are returned with PUT. This requires the
    previous terms be queried. The differences between the old and the
    new term sets determines which old terms are deleted and which new
    terms are added to the index. ADD and DELETE do not require the
    previous terms be queried.
    """
    assert self.col_def.indexer and \
        isinstance(self.col_def.indexer, indexers.SecondaryIndexer)
    update = self.Update()
    # Create the term dict.
    term_dict = {}
    if update.value is not None:
      for term in update.value:
        term_dict.update(self.col_def.indexer.Index(self.col_def, term).items())
    return db_client.UpdateAttr(value=term_dict, action=update.action)


class _KeyValue(_SingleValue):
  """Holds a column with a single value (such as a string, a timestamp, etc.).
  """
  def Set(self, value):
    if self._value is None and value is not None:
      self._CheckType(value)
      self.SetModified(True)
      self._value = value
    elif self._value != value:
      assert False, "cannot modify a key value: %s=>%s" % (self._value, repr(value))

  def Update(self):
    """Key values are not updated. On creation, the key is already
    specified as part of the request.
    """
    assert self.IsModified()
    return None


class Column(object):
  """A single-value column.

  The '_type' values are specified as 'struct' format characters:
  http://docs.python.org/library/struct.html
  """
  def __init__(self, name, key, value_type, indexer=None, read_only=False):
    self.name = name.lower()
    self.key = key.lower()
    self.value_type = value_type
    self.read_only = read_only
    self.indexer = indexer
    # The back link to the table is set by the containing table.
    self.table = None

  def NewInstance(self):
    return _SingleValue(self)


class HashKeyColumn(Column):
  """A column to designate the primary key of a row in the datastore.
  In DynamoDB, this is referred to as the 'hash-key', and is used to
  randomly & uniformly disperse items in a particular table across the
  key range.
  """
  def __init__(self, name, key, value_type):
    super(HashKeyColumn, self).__init__(name, key, value_type, indexer=None)

  def NewInstance(self):
    return _KeyValue(self)


class RangeKeyColumn(Column):
  """A column to designate the secondary key of a row in the datastore.
  In DynamoDB, this is referred to as the 'range-key', and is used to
  provide a sort order on items with identical 'hash-key' values.
  """
  def __init__(self, name, key, value_type, indexer=None):
    super(RangeKeyColumn, self).__init__(name, key, value_type, indexer=indexer)

  def NewInstance(self):
    return _KeyValue(self)


class SetColumn(Column):
  """A subclass of column whose column value in the datastore is a
  set of values, each with value as specified by value_type.
  """
  def __init__(self, name, key, value_type, indexer=None, read_only=False):
    super(SetColumn, self).__init__(name, key, value_type, indexer=indexer, read_only=read_only)

  def NewInstance(self):
    return _SetValue(self)


class IndexTermsColumn(Column):
  """A subclass of column for the list of index terms generated by an
  indexed column. These columns are special in that they don't actually
  create an instance of a value class to hold the contents. They are
  ephemeral and exist only in the database; they cannot be accessed via
  the column name on a DBObject, as for all other column types.

  The value type is always a string set 'SS'.
  """
  def __init__(self, name, key):
    super(IndexTermsColumn, self).__init__(name, key, 'SS', indexer=False)

  def NewInstance(self):
    raise TypeError('IndexTermsColumn is ephemeral')


class LatLngColumn(Column):
  """Column subclass to handle geographic coordinates measured in
  degrees of latitude and longitude. An accuracy is also include,
  measured in meters. Stores values as double precision floating point
  numbers via struct. The results are base64hex encoded for storage in
  the backend datastore. Takes either a LocationIndexer or
  BreadcrumbIndexer depending on the type of geo search desired.
  """
  def __init__(self, name, key, indexer=None):
    """Creates a geographic location indexer if 'indexed'."""
    if indexer is not None:
      assert isinstance(indexer, indexers.BreadcrumbIndexer) or \
          isinstance(indexer, indexers.LocationIndexer)
    super(LatLngColumn, self).__init__(name, key, 'S', indexer=indexer)

  def NewInstance(self):
    return _LatLngValue(self)


class PlacemarkColumn(Column):
  """Column to handle hiearchical place names from country to street-
  level. Stores value as comma-separated url-quoted string value in
  datastore, but makes value available via a namedtuple. If indexer
  is not None, must be of type PlacemarkIndexer.
  """
  def __init__(self, name, key, indexer=None):
    if indexer is not None:
      assert isinstance(indexer, indexers.PlacemarkIndexer)
    super(PlacemarkColumn, self).__init__(name, key, 'S', indexer)

  def NewInstance(self):
    return _PlacemarkValue(self)


class JSONColumn(Column):
  """Column to handle JSON-encoded python data structure.
  """
  def __init__(self, name, key, read_only=False):
    super(JSONColumn, self).__init__(name, key, 'S', indexer=None, read_only=read_only)

  def NewInstance(self):
    return _JSONValue(self)


class CryptColumn(Column):
  """Column with contents that are encrypted with the service-wide db
  crypt key.
  """
  def __init__(self, name, key):
    super(CryptColumn, self).__init__(name, key, 'S', None)

  def NewInstance(self):
    return _CryptValue(self)


class Table(object):
  """A table contains an array of Column objects."""
  VERSION_COLUMN = Column('_version', '_ve', 'N')

  def __init__(self, name, key, read_units, write_units, columns, name_in_db=None):
    # Add special column for _version, used in migrating the data model
    # as new features demand.
    columns.append(Table.VERSION_COLUMN)
    # Set up back links in each column definition to this table. The columns
    # need the back link for the table key when they generate index terms.
    for c in columns:
      c.table = self
    self.name = name
    self.name_in_db = name_in_db if name_in_db else name
    self.key = key
    self._VerifyColumns(columns)
    self._all_column_names = [c.name for c in columns]
    self._column_names = [c.name for c in columns if not isinstance(c, IndexTermsColumn)]
    self._columns = dict([(c.name, c) for c in columns])
    self._key_to_name = dict([(c.key, c.name) for c in columns])
    self.read_units = read_units
    self.write_units = write_units
    self.hash_key_col = columns[0]
    self.hash_key_schema = db_client.DBKeySchema(
      name=self.hash_key_col.key, value_type=self.hash_key_col.value_type)
    if len(columns) > 1 and isinstance(columns[1], RangeKeyColumn):
      self.range_key_col = columns[1]
      self.range_key_schema = db_client.DBKeySchema(
        name=self.range_key_col.key, value_type=self.range_key_col.value_type)
    else:
      self.range_key_col = None
      self.range_key_schema = None

  def GetColumnName(self, key):
    """Returns the column name for a column key."""
    return self._key_to_name[key]

  def GetColumnNames(self, all_columns=False):
    """Returns a list of column names (sorted in original order). Specify
    'all_columns' as True to include index term columns as well.
    """
    if all_columns:
      return self._all_column_names
    else:
      return self._column_names

  def GetColumns(self, all_columns=False):
    """Returns a list of column definitions. Specify 'all_columns' as True
    to include index term columns as well.
    """
    if all_columns:
      return self._columns.values()
    else:
      return [c for c in self._columns.values() if not isinstance(c, IndexTermsColumn)]

  def GetColumn(self, name):
    """Returns the named column definition. Column names are not case
    sensitive.
    """
    return self._columns[name.lower()]

  def GetColumnByKey(self, key):
    """Returns the column definition by key.
    """
    return self._columns[self._key_to_name[key]]

  def _VerifyColumns(self, columns):
    """Verifies the columns are appropriately configured.

    - First column is a HashKeyColumn
    - Only second column may be a RangeKeyColumn
    - All column names are unique
    - All column keys are unique
    - If any columns are indexed, table is IndexedTable
    - SetColumns may only use SecondaryIndexer
    """
    # Verify only one ID column, the first.
    assert isinstance(columns[0], HashKeyColumn)
    column_keys = set([columns[0].key])
    column_names = set([columns[0].name])
    for i in xrange(1, len(columns)):
      c = columns[i]
      assert not isinstance(c, HashKeyColumn)
      if i >= 2:
        assert not isinstance(c, RangeKeyColumn)
      assert c.name not in column_names, (c.name, column_names)
      column_names.add(c.name)
      assert c.key not in column_keys, c.key
      column_keys.add(c.key)
      if c.indexer:
        assert isinstance(self, IndexedTable)
        if isinstance(c, SetColumn):
          assert isinstance(c.indexer, indexers.SecondaryIndexer)


class IndexedTable(Table):
  """A table whose data is indexed. An indexed table may not use a
  composite key. Each column can specify an optional indexing function
  ('indexer' to each column definition).  The indexer transforms the
  column value into a set of terms, each of which is inserted into an
  index table, which has a composite key of hash-key=term,
  range-key=obj_key. The data is for the column is optional, but might
  include term positions in the document, for example, to support
  phrase searches.

  Using an indexed table, you can create a full-text search over table
  data (e.g. the captions of all images), or an arbitrary secondary
  index (e.g., an ordinal popularity ranking of photos).

  When an indexer generates index terms for a column, the terms are
  stored near the column data for subsequent reference. For example,
  if the column data are modified, the old terms are compared against
  the new terms. Terms which have been discarded (diff between old and
  new) are deleted from the index table. Terms which have been added
  (diff between new and old) are added to the index table. This also
  solves the problem of how to handle changes in the indexers, which
  might make it impossible to re-derive the previous set of index
  terms in order to delete them.

  For each indexed column we generate an additional column to hold the
  list of indexed terms. These are ephemeral and not accessible via
  the normal DBObject getters and setters.
  """
  def __init__(self, name, key, read_units, write_units, columns, name_in_db=None):
    index_term_cols = [IndexTermsColumn(c.name + ':t', c.key + ':t') for c in columns if c.indexer]
    columns += index_term_cols
    super(IndexedTable, self).__init__(name, key, read_units, write_units, columns, name_in_db=name_in_db)


class IndexTable(Table):
  """A table used to store reverse index data. This is a composite key
  table with the indexed term as the hash key and the doc-id as the
  range key. Depending on the application, the doc-id may be an
  amalgamation of object key and some other value to affect the order
  in which results are fed to the query evaluator. Most commonly, the
  doc-id is prefixed with a 'reversed' timestamp to yield doc-ids from
  posting lists in order of most to least recent. The type (whether a
  string or a number) are specified for both the term and the doc-id
  to the constructor.
  """
  def __init__(self, name, term_type, key_type, read_units, write_units, scan_limit=50, name_in_db=None):
    super(IndexTable, self).__init__(name, 'ix', read_units, write_units,
                                     [HashKeyColumn('term', 't', term_type),
                                      RangeKeyColumn('key', 'k', key_type),
                                      Column('data', 'd', 'S')], name_in_db=name_in_db)
    self.scan_limit = scan_limit


class Schema(object):
  """A collection of table definitions. Table names are not case sensitive."""
  def __init__(self, tables):
    """A schema based on the provided sequence of table definitions."""
    # Create dictionary mapping from table name to table instance. Due to upgrades, some tables
    # may have a different name in the database, so create a set of those names to be used
    # during verification.
    self._tables = dict()
    self._tables_in_db = dict()
    for table in tables:
      self.AddTable(table)

  def GetTables(self):
    """Returns a list of tables in the schema."""
    return sorted(self._tables.values())

  def GetTable(self, table):
    """Returns the descriptor for the named table."""
    return self._tables[table.lower()]

  def TranslateNameInDb(self, name_in_db):
    """Given the name of a table in the database, translate to the name
    for that table that the application uses (which may be different if
    we've done an upgrade). If the table exists in the database, but not
    in the application, just return the name in the database.
    """
    key = name_in_db.lower()
    return self._tables_in_db[key].name if key in self._tables_in_db else name_in_db

  def AddTable(self, table):
    """Adds the specified table to the schema."""
    assert table.name not in self._tables, table
    assert table.name_in_db not in self._tables_in_db, table
    self._tables[table.name.lower()] = table
    self._tables_in_db[table.name_in_db.lower()] = table

  def VerifyOrCreate(self, client, callback, verify_only=False):
    """Verifies the schema if it exists or creates it if not.
    Verification checks existing tables match the schema definition,
    warns of vestigial tables, and creates any tables which are
    missing.

    Vestigial tables may be deleted by specifying the --delete_vestigial
    command line flag.

    On completion, invokes callback with a list of verified table schemas.
    """
    def _OnDescribeTable(table, verify_cb, result):
      """Verifies the table description in schema matches the
      table in the database.
      """
      if verify_only:
        verify_cb((table.name, result))
        return

      assert isinstance(result, db_client.DescribeTableResult), result
      if options.options.verify_provisioning:
        # TODO(mike): Longer term, consider using values read from dymamodb for provisioned throughput as authoritative
        #   or consider some other mechanism for monitoring mismatches. We shouldn't prevent server startup just
        #   because of a mismatch in provisioned read or write units.
        if table.read_units != result.schema.read_units:
          logging.warning('%s: read units mismatch %d != %d', table.name, table.read_units, result.schema.read_units)
        if table.write_units != result.schema.write_units:
          logging.warning('%s: write units mismatch %d != %d', table.name, table.write_units, result.schema.write_units)
      assert table.hash_key_schema == result.schema.hash_key_schema, \
          '%s: hash key schema mismatch %r != %r' % \
          (table.name, table.hash_key_schema, result.schema.hash_key_schema)
      assert table.range_key_schema == result.schema.range_key_schema, \
          '%s: range key schema mismatch %r != %r' % \
          (table.name, table.range_key_schema, result.schema.range_key_schema)
      assert result.schema.status in ['CREATING', 'ACTIVE'], \
          '%s: table status invalid: %s' % (table.name, result.schema.status)
      if result.schema.status == 'CREATING':
        logging.info('table %s still in CREATING state...waiting 1s' % table.name)
        client.AddTimeout(1.0, partial(_VerifyTable, table, verify_cb))
        return
      else:
        logging.debug('verified table %s' % table.name)
      verify_cb((table.name, result))

    def _VerifyTable(table, verify_cb):
      """Gets table description and verifies via _OnDescribeTable."""
      client.DescribeTable(table=table.name,
                           callback=partial(_OnDescribeTable, table, verify_cb))

    def _OnCreateTable(table, verify_cb, result):
      """Invoked on creation of a table; moves to verification step."""
      assert isinstance(result, db_client.CreateTableResult), result
      logging.debug('created table %s: %s' % (table.name, repr(result.schema)))
      _VerifyTable(table, verify_cb)

    def _OnListTables(result):
      """First callback with results of a list-tables command.
      Creates a results barrier which will collect all table schemas
      and return 'callback' on successful verification of all tables.
      """
      # Create and/or verifies all tables in schema.
      with util.ArrayBarrier(callback) as b:
        read_capacity = 0
        write_capacity = 0
        for table in self._tables.values():
          read_capacity += table.read_units
          write_capacity += table.write_units
          if table.name not in result.tables:
            if verify_only:
              b.Callback()((table.name, None))
            else:
              logging.debug('creating table %s...' % table.name)
              client.CreateTable(table=table.name, hash_key_schema=table.hash_key_schema,
                                 range_key_schema=table.range_key_schema,
                                 read_units=table.read_units, write_units=table.write_units,
                                 callback=partial(_OnCreateTable, table, b.Callback()))
          else:
            _VerifyTable(table, b.Callback())

      # Warn of vestigial tables.
      for table in result.tables:
        if table.lower() not in self._tables:
          logging.warning('vestigial table %s exists in DB, not in schema' % table)
          if options.options.delete_vestigial and options.options.localdb:
            logging.warning('deleting vestigial table %s')
            client.DeleteTable(table=table, callback=util.NoCallback)

      # Cost metric.
      def _CostPerMonth(units, read=True):
        return 30 * 24 * 0.01 * (units / (50 if read else 10))

      logging.debug('total tables: %d' % len(self._tables))
      logging.debug('total read capacity: %d, $%.2f/month' % (read_capacity, _CostPerMonth(read_capacity, True)))
      logging.debug('total write capacity: %d, $%.2f/month' % (write_capacity, _CostPerMonth(write_capacity, False)))

    client.ListTables(callback=_OnListTables)
