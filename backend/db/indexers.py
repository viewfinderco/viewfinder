# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Indexers.

Indexers transform database column (aka attribute) values into index
terms for a reverse index.

  Indexer: creates secondary index(es) for a column [abstract]
  SecondaryIndexer: simplest indexer for implementing secondary indexes
  LocationIndexer: indexes location across all S2 cell resolutions
  BreadcrumbIndexer: indexes location at a specific (50m-radius) S2 resolution
  LocationIndexer: indexes location by emitting S2 patches
  PlacemarkIndexer: indexes hierarchical place names
  FullTextIndexer: separate col value via white-space for full-text search
  EmailTokenizer: tokenizes email addresses
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import s2
import re
import struct

from viewfinder.backend.base import base64hex
from viewfinder.backend.base.util import ConvertToString
from viewfinder.backend.db import stopwords

try:
  # We have two double metaphone implementations available:
  # The one in "fuzzy" is faster, but doesn't work on pypy.
  import fuzzy
  _D_METAPHONE = fuzzy.DMetaphone()
except ImportError:
  import metaphone
  _D_METAPHONE = metaphone.doublemetaphone

class Indexer(object):
  """An indexer creates arbitrary secondary indexes for a column by
  transforming the column value into a set of index terms. Each index
  term will be stored as a link back to the object containing the
  column. The set of index terms are actually the keys to a python
  dict, with value being an opaque datum to be retrieved in addition
  to the primary key of the object (more on the utility of this below).

  The simplest example of an Indexer would return the exact value of
  the column. This is equivalent to creating a secondary key on the
  column in a relational database. The object can now be queried by
  this column's value in addition to the primary key value.

  Full text search can be implemented by parsing column values by
  whitespace, and emitting the resulting words as index terms. In this
  case, the datum accompanying the index terms would be a list of word
  positions, for implementing phrase searches.

  Another illustrative example would be an indexer for location, as
  specified by a (longitude, latitude, accuracy) tuple. This might
  yield a set of S2 geometry patches, each locating the image in a
  successively more exact region of the earth from, for example,
  continent to city block.

  Only "field-specific" index terms are allowed. This means that every
  index term emitted while indexing a column is prefixed with the
  table key and the column key. This prevents term collisions between
  tables--and within a table--between columns, which would otherwise
  confuse or break phrase searches, and would cause headaches when
  updating columns (you'd either need to ref-count or to do wholesale
  updates/deletes of objects instead of allowing incremental updates.

  Columns which hold a set of values (e.g. a set of user email addresses
  used as login identities), may only use the SecondaryIndexer, which
  very simply emits the column value as the only index term. Since the
  column is a set, the column value yields a unique index term--which
  means it works properly with incremental set additions and deletions
  so we can have arbitrarily large sets. If you do need to whitespace
  tokenize an email address (to continue the example), then create a
  field(s) for primary email address, secondary email address, etc.,
  which can set whatever tokenizer they like.
  """

  class Option:
    """Class enum for whether this tokenizer should include various
    expansions. The allowed values are one of:

    'NO': do not include terms for this option
    'YES': include terms both for this option and without
    'ONLY': only include terms for this option
    """
    NO, YES, ONLY = range(3)

  def Index(self, col, value):
    """Parses the provided value into a dict of {tokenized term:
    freighted data}. By default, emits the column value as the only
    index term. Subclasses override for specific behavior.
    """
    return dict([(t, None) for t in self._ExpandTerm(col, value)])

  def GetQueryString(self, col, value):
    """Returns a query string suitable for the query parser to match
    the specified value. In most cases, this is simply the term
    itself, prefixed with the key + ':'. However, for full-text
    search, this would generate a succession of 'and's for phrase
    searches and potentially 'or's in cases where a term has homonyms,
    as in metaphone expansions.
    """
    exp_terms = self._ExpandTerm(col, value)
    return exp_terms[0] if len(exp_terms) == 1 \
        else '(' + ' | '.join(exp_terms) + ')'

  def UnpackFreight(self, col, posting):
    """Returns a value representing the unpacked contents of data that
    were freighted with the posting of this term. This is tokenizer-
    dependent. For example, the FullTextIndexer freights a list
    of word positions.
    """
    return None

  def _InterpretOption(self, option, term, optional_term):
    """Returns either the first, second or both terms from the list
    depending on the value of option.
    """
    if option == Indexer.Option.NO:
      return [term]
    elif option == Indexer.Option.ONLY:
      return [optional_term]
    elif option == Indexer.Option.YES:
      return [term, optional_term]
    raise TypeError()

  def _ExpandTerm(self, col, term):
    """Expands each term in 'terms'. In the base class, this merely
    prepends the table key + ':' + column key + ':' to each term.
    """
    prefix = col.key + ':'
    if col.table:
      prefix = col.table.key + ':' + prefix
    return [prefix + ConvertToString(term)]


class SecondaryIndexer(Indexer):
  """An indexer class which simply emits the column value."""
  def GetQueryString(self, col, value):
    """Returns a quoted string to match the column value exactly.
    """
    exp_terms = self._ExpandTerm(col, value)
    assert len(exp_terms) == 1
    return '"%s"' % exp_terms[0]


class TimestampIndexer(Indexer):
  """An indexer class which emits tokens to support queries over
  time intervals.
  TODO(spencer): fix this; currently only works with exact time
  """
  def Index(self, col, value):
    """Parses the provided value into a dict of {tokenized term:
    freighted data}. By default, emits the column value as the only
    index term. Subclasses override for specific behavior.
    """
    return dict([(t, None) for t in self._ExpandTerm(col, int(value))])

  def GetQueryString(self, col, value):
    """
    """
    exp_terms = self._ExpandTerm(col, int(value))
    assert len(exp_terms) == 1
    return '"%s"' % exp_terms[0]


class BreadcrumbIndexer(Indexer):
  """Indexer for user breadcrumbs. On indexing, each breadcrumb
  generates a sequence of S2 geometry cells at the specified
  S2_CELL_LEVEL cell level to cover a radius of
  RADIUS. On query, only a single patch is generated at
  S2_CELL_LEVEL to minimize the search read requirements.
  """
  RADIUS = 51
  S2_CELL_LEVEL = s2.GetClosestLevel(RADIUS)

  def Index(self, col, value):
    """Generates implicated S2 patches at S2_CELL_LEVEL which cover an
    S2 cap centered at lat/lon with radius RADIUS.
    """
    lat, lon, acc = value
    cells = [c for c in s2.SearchCells(
        lat, lon, BreadcrumbIndexer.RADIUS,
        BreadcrumbIndexer.S2_CELL_LEVEL, BreadcrumbIndexer.S2_CELL_LEVEL)]
    assert len(cells) <= 10, len(cells)
    return dict([(t, None) for c in cells for t in self._ExpandTerm(col, c)])

  def GetQueryString(self, col, value):
    """The provided value is a latitude, longitude, accuracy
    tuple. Returns a search query for the indicated S2_CELL_LEVEL cell.
    """
    lat, lon, acc = [float(x) for x in value.split(',')]
    cells = s2.IndexCells(lat, lon, BreadcrumbIndexer.S2_CELL_LEVEL,
                          BreadcrumbIndexer.S2_CELL_LEVEL)
    assert len(cells) == 1, [repr(c) for c in cells]
    exp_terms = self._ExpandTerm(col, cells[0])
    return exp_terms[0] if len(exp_terms) == 1 \
        else '(' + ' | '.join(exp_terms) + ')'


class LocationIndexer(Indexer):
  """An indexer class which emits S2 patch values at various
  resolutions corresponding to a latitude/longitude/accuracy tuple.

  The resolution goes from 10m to 1000km, which is roughly s2 patch
  levels 3 to 25.
  """
  _S2_MIN = 3
  _S2_MAX = 25

  def Index(self, col, value):
    """Generates implicated S2 patches from levels (_S2_MIN, _S2_MAX).
    """
    lat, lon, acc = value
    cells = [c for c in s2.IndexCells(
        lat, lon, LocationIndexer._S2_MIN, LocationIndexer._S2_MAX)]
    cells.reverse()
    return dict([(t, None) for c in cells for t in self._ExpandTerm(col, c)])

  def GetQueryString(self, col, value):
    """The provided value is a triplet of latitude, longitude and a
    radius in meters. Returns an 'or'd set of S2 geometry patch terms
    that cover the region.
    """
    lat, lon, rad = [float(x) for x in value.split(',')]
    cells = [c for c in s2.SearchCells(lat, lon, rad, LocationIndexer._S2_MIN,
                                       LocationIndexer._S2_MAX)]
    exp_terms = [t for c in cells for t in self._ExpandTerm(col, c)]
    return exp_terms[0] if len(exp_terms) == 1 \
        else '(' + ' | '.join(exp_terms) + ')'


class PhraseSearchIndexer(Indexer):
  """A base class for indexing values where relative position of
  tokens is important and the indexer must support phrase searches,
  such as the full-text indexer and the placemark indexer.

  Sub-classes must implement _Tokenize().
  """
  def Index(self, col, value):
    """Returns words as contiguous alpha numeric strings (and
    apostrophes) which are of length > 1 and are also not in the stop
    words list. Each term is freighted with a list of term positions
    (formatted as a packed binary string).
    """
    terms = {}
    expansions = {}  # map from term to expanded set of terms
    tokens = self._Tokenize(value)
    for pos, term in zip(xrange(len(tokens)), tokens):
      if term == '_':
        continue
      if term not in expansions:
        expansions[term] = self._ExpandTerm(col, term)
      for exp_term in expansions[term]:
        if not terms.has_key(exp_term):
          terms[exp_term] = ''
        if pos < 1<<16:
          terms[exp_term] += struct.pack('>H', pos)

    # Base64Hex Encode positions.
    for k,v in terms.items():
      if v:
        terms[k] = base64hex.B64HexEncode(v, padding=False)

    return terms

  def GetQueryString(self, col, value):
    """Returns a query string suitable for the query parser to match
    the specified value. If the value tokenizes to multiple terms,
    generates a conjunction of '+' operators which is like '&", but
    with a positional requirement (this implements phrase
    search). Each term is then expanded into a conjunction of 'or'
    operators.
    """
    def _GetExpansionString(term):
      if term == '_':
        return term
      exp_terms = self._ExpandTerm(col, term)
      if len(exp_terms) == 1:
        return exp_terms.pop()
      else:
        return '(' + ' | '.join(exp_terms) + ')'

    tokens = self._Tokenize(value)
    if len(tokens) == 1:
      return _GetExpansionString(tokens[0])
    else:
      return '(' + ' + '.join([_GetExpansionString(token) for token in tokens]) + ')'

  def UnpackFreight(self, col, posting):
    # TODO(spencer): the rstrip() below is necessary as data in the
    # index has already been encoded with a bug in the base64 padding
    # We need to rebuild the index before reverting this.
    posting = base64hex.B64HexDecode(posting.rstrip('='), padding=False)
    assert not (len(posting) % 2), repr(posting)
    return [struct.unpack('>H', posting[i:i+2])[0] for i in xrange(0, len(posting), 2)]


class PlacemarkIndexer(PhraseSearchIndexer):
  """An indexer class which emits index terms for each hierarchical
  name in a placemark structure.

  Phrase searching is supported by reversing the placemark names from
  least to most specific (so "Paris, France" and "New York, NY" work
  properly).

  TODO(spencer): provide an additional mechanism for searching
  specifically for country=X, etc.
  """
  _SPLIT_CHARS = re.compile("[^a-z0-9 ]")

  def Index(self, col, value):
    places = value._asdict().values()
    places.reverse()
    return super(PlacemarkIndexer, self).Index(col, ' '.join(places))

  def _Tokenize(self, value):
    """Strips all punctuation characters and tokenizes by whitespace."""
    return PlacemarkIndexer._SPLIT_CHARS.sub('', value.lower()).split()


class FullTextIndexer(PhraseSearchIndexer):
  """An Indexer class meant for creating index terms for full-text
  search. Provides an optional facility for normalizing english words
  to a phonetic system to easily correct for mispellings.

  Uses non-alpha-numeric characters to split the value into words,
  filters out English stop words, and returns a sequence of (term,
  struct-packed position) pairs. The struct-packed position list uses
  two bytes for each position. It only applies to the first 65536
  words.

  Shout out to: http://dr-josiah.blogspot.com/2010/07/
  building-search-engine-using-redis-and.html
  """
  _SPLIT_CHARS = re.compile("[^a-z0-9' ]")

  def __init__(self, metaphone=Indexer.Option.NO):
    """- metaphone: generate metaphone query terms. Metaphone is an
         expansive phonetic representation of english language words.
    """
    super(FullTextIndexer, self).__init__()
    self._metaphone = metaphone

  def _Tokenize(self, value):
    """Splits 'value' into a sequence of (position, token) tuples
    according to whitespace. Stop words are represented by the '_' character.
    """
    tokens = FullTextIndexer._SPLIT_CHARS.sub(' ', value.lower()).split()
    tokens = [token.strip("'") for token in tokens]
    for i in xrange(len(tokens)):
      if tokens[i] in stopwords.STOP_WORDS or len(tokens[i]) == 1:
        tokens[i] = '_'
    return tokens

  def _ExpandTerm(self, col, term):
    """Expand term according to metaphone and then for each, expand
    using Indexer._ExpandTerm.
    """
    terms = set()
    for meta_term in self.__ExpandMetaphone(term):
      if meta_term:
        terms = terms.union(Indexer._ExpandTerm(self, col, meta_term))
    return terms

  def __ExpandMetaphone(self, term):
    """Expands term according to metaphone setting. Need to be careful
    here about the metaphone algorithm returning no matches, as is the
    case with numbers and sufficiently non-English words. In this
    case, where there are no metaphone results, we just add the term.
    """
    if self._metaphone == Indexer.Option.NO:
      return set([term])
    else:
      terms = set()
      for dmeta_term in _D_METAPHONE(term):
        if dmeta_term:
          terms = terms.union(self._InterpretOption(
              self._metaphone, term, dmeta_term))
      if not terms:
        terms.add(term)
      return terms


class EmailIndexer(FullTextIndexer):
  pass
