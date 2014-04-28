# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Parses query expressions into hierarchical query trees.

Given a data schema (defined via schema.py), you can create Query objects
and execute them against a database client. For example, with table 'User'
and columns 'given_name' and 'Email', you can run a query as follows:

  query_str = '(user.given_name=spencer | user.given_name="andrew") & user.family_name=kimball'
  users = User.Query(query_str).Evaluate(client)


  Query: query object to evaluate query expression.

Supports parameterized phrases which should be used with strings from an untrusted source in order to mitigate
injection attacks.  The keys are valid in the phrase part of the query where the key name is surrounded by braces.
Parameterized queries are passed as a tuple where the first element is the query string followed by a dictionary
with the parameter keys mapped to parameter values.  The above query expression using parameters:

  bound_query_str = ('(user.given_name={p1} | user.given_name={p2}) & user.family_name={p3}',
                     {'p1': 'spencer', 'p2': 'andrew', 'p3': 'kimball'})

The parameter keys may be made up of letters, digits, and the underscore (_).

Based on calculator.py by Andrew Brehaut & Steven Ashley of picoparse.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging
import re

from bisect import bisect_left, bisect_right
from collections import namedtuple
from functools import partial
from picoparse import one_of, choice, many1, tri, commit, p, many_until1
from picoparse.text import run_text_parser, as_string, lexeme, whitespace, quoted
from string import digits, letters
from tornado import escape
from viewfinder.backend.base import util
from viewfinder.backend.db import db_client, vf_schema
from viewfinder.backend.db.schema import IndexedTable

_query_cache = util.LRUCache(100)

# Optimization for the common case:  Indexer.GetQueryString usually returns a single token
# as a quoted string.  Picoparse's character-by-character operation is slow, so bypass
# it when we can.
_QUOTED_TOKEN_RE = re.compile(r'^"([^"\\]*)"$')

class _MatchResult(object):
  """The result of a successful match after node evaluation. Data
  initially contains the value attached to a key in a posting list,
  but may be arbitrarily updated and augmented as it moves through the
  query tree.
  """
  __slots__ = ['key', 'data']

  def __init__(self, key, data):
    self.key = key
    self.data = data

  def __cmp__(self, other):
    return cmp(self.key, other.key)


# The result from evaluating a node or subtree of the query tree.
# Matches is a list of '_MatchResult' values. 'last_key' is the
# last key in the range which was successfully evaluated.
_EvalResult = namedtuple('_EvalResult', ['matches', 'last_key', 'read_units'])


class _QueryNode(object):
  """Query nodes form binary trees with set operations at each
  intermediate node and ranges of keys at leaf nodes.
  """
  pass


class _OpNode(_QueryNode):
  """Operation nodes implement set operations on the results of
  key range queries. Set operations include union, difference and
  intersection.
  """
  def __init__(self, schema, left):
    """Takes the left child as a parameter. The right child is merged
    into this operation via a call to Merge. The two are followed
    recursively during evaluation, with the left and right evaluated
    asynchronously. When both have completed, the result of the set
    operation (union, difference, intersection & positional intersection)
    is evaluated and returned to parent.
    """
    self._left = left
    self._right = None

  def PrintTree(self, level, param_dict):
    """Depth-first printout of tree structure for debugging."""
    return self._OpName() + ' __ ' + self._left.PrintTree(level + 1, param_dict) + '\n' + level * ('     ') + \
                            '  \_ ' + self._right.PrintTree(level + 1, param_dict)

  def Merge(self, right):
    """Rearranges the parent-child relationship to conform to operator
    precedence. If the precedence of the current node is >= the node
    to its right, then the right-hand node becomes the new parent,
    with the current node made its new left-hand node (meaning this
    node will be evaluated first, as the evaluation is a depth-first
    traversal). Otherwise, the right-hand node simply stays the right
    hand node.
    """
    if self._precedence >= right._precedence:
      self._right = right._left
      right._left = self
      return right
    else:
      self._right = right
      return self

  def Evaluate(self, client, callback, start_key, consistent_read, param_dict):
    """Recursively evaluates the query tree via a depth- first
    traversal. Returns the result set, defined by the data delivered
    via the IndexTermNodes and then operated on by the OpNodes.
    """
    with util.ArrayBarrier(partial(self._SetOperation, callback)) as b:
      self._left.Evaluate(client, b.Callback(), start_key, consistent_read, param_dict)
      self._right.Evaluate(client, b.Callback(), start_key, consistent_read, param_dict)

  def _OpName(self):
    raise NotImplementedError()

  def _SetOperation(self):
    raise NotImplementedError()


class Union(_OpNode):
  """Returns the union of two sets. Lowest precedence."""
  def __init__(self, schema, left):
    super(Union, self).__init__(schema, left)
    self._precedence = 0

  def _OpName(self):
    return "| "

  def _SetOperation(self, callback, results):
    """For union, the sets are additively combined. Both the first and
    last keys are defined as the minimum of first and last keys for
    the two results. This jibes well with the intuitive notion that we
    were able to successfully evaluate the union between these two
    sets for all values starting at the very minimum up to and
    including the minimum of the two last keys. This prevents us from
    over-stepping a gap between the two ranges for example.
    """
    assert len(results) == 2
    matches = results[0].matches + results[1].matches
    matches.sort()

    if results[0].last_key is None:
      last_key = results[1].last_key
    elif results[1].last_key is None:
      last_key = results[0].last_key
    else:
      last_key = min(results[0].last_key, results[1].last_key)

    # Only returns matches up to last_key.
    if last_key:
      matches = matches[:bisect_right(matches, _MatchResult(last_key, None))]
    callback(_EvalResult(matches=matches, last_key=last_key,
                         read_units=results[0].read_units + results[1].read_units))


class Difference(_OpNode):
  """Returns the difference of two sets."""
  def __init__(self, schema, left):
    super(Difference, self).__init__(schema, left)
    self._precedence = 1

  def _OpName(self):
    return "- "

  def _SetOperation(self, callback, results):
    """For set difference, the ordering matters. The second set can be
    thought of as a mask over the first set. The overlap starting at
    the first key and extending to the min(last_key1, last_key2) defines
    the successfully-evaluated range. To see this, consider that any
    portion of the subtracted range which lies before the first set is
    irrelevant (as we can only eval what we have of the first range
    going forward), and any portion of the subtracted range which lies
    after the first set can't yet be evaluated, as we don't yet know
    the remainder of the first set.
    """
    assert len(results) == 2
    m1 = results[0].matches
    m2 = results[1].matches
    matches = []
    while m1:
      m2_idx = bisect_left(m2, m1[0])
      if m2_idx == len(m2):
        break
      elif m1[0] == m2[m2_idx]:
        # A match, so skip.
        m1 = m1[1:]
      elif m2_idx == 0:
        # No match, so include the range of m1's up to the start of m2.
        m1_idx = bisect_left(m1, m2[0])
        if m1_idx == len(m1):
          # The last result of m1 is still before the next m2; include all.
          matches += m1
          break
        else:
          # Include up to the next possible match between m1 and m2.
          matches += m1[:m1_idx]
          m1 = m1[m1_idx:]

    if results[0].last_key is None:
      last_key = results[1].last_key
    elif results[1].last_key is None:
      last_key = results[0].last_key
    else:
      last_key = min(results[0].last_key, results[1].last_key)
    callback(_EvalResult(matches=matches, last_key=last_key,
                         read_units=results[0].read_units + results[1].read_units))


class Intersection(_OpNode):
  """Returns the intersection of two sets."""
  def __init__(self, schema, left):
    super(Intersection, self).__init__(schema, left)
    self._precedence = 2

  def _OpName(self):
    return "& "

  def _SetOperation(self, callback, results):
    """Efficiently skip through the two lists using list bisection.
    """
    assert len(results) == 2
    m1 = results[0].matches
    m2 = results[1].matches
    matches = []
    while m1 and m2:
      if m1[0] < m2[0]:
        m1 = m1[bisect_left(m1, m2[0]):]
      elif m2[0] < m1[0]:
        m2 = m2[bisect_left(m2, m1[0]):]
      else:
        matches.append(m1[0])
        m1 = m1[1:]
        m2 = m2[1:]

    callback(_EvalResult(matches=matches, last_key=self._ComputeLastKey(results),
                         read_units=results[0].read_units + results[1].read_units))

  def _ComputeLastKey(self, results):
    """For set intersection, the successfully-evaluated portion starts
    at the maximum of the first keys and extends as far as the minimum
    of the last keys. This is the portion for which we have enough
    information to definitively determine intersection.
    """
    if results[0].last_key is None:
      last_key = results[1].last_key
    elif results[1].last_key is None:
      last_key = results[0].last_key
    else:
      last_key = min(results[0].last_key, results[1].last_key)
    return last_key


class PositionalIntersection(Intersection):
  """Returns the intersection of two posting lists, but only return
  matches where relative positions between the left and right nodes
  are self._delta apart.
  """
  def __init__(self, schema, left):
    super(PositionalIntersection, self).__init__(schema, left)
    self._delta = 1

  def Merge(self, right):
    """Merging for positional intersections works a little differently
    than for normal operations. Here, we are on the lookout to merge
    place-holder (None) nodes out of the tree. If the right-hand node
    we're trying to merge is a place-holder, then return the left-hand
    node as the result of the merge (this removes trailing
    place-holders). If the right-hand node we're merging's left-hand
    node is a place-holder, we skip over the right-hand node by
    attaching its right-hand node in its place. This operation
    increases our delta by the delta of the now-merged right-hand node.
    """
    if right is None:
      return self._left
    elif isinstance(right, PositionalIntersection) and right._left is None:
      self._delta += right._delta
      self._right = right._right
    else:
      self._right = right
    return self

  def _OpName(self):
    return "+%d" % self._delta

  def _SetOperation(self, callback, results):
    """Perform a standard intersection operation, but on a match,
    return only the left node's position data, and then only those
    positions with a difference of self._delta from the right node's
    positions.
    """
    assert len(results) == 2
    m1 = results[0].matches
    m2 = results[1].matches
    matches = []
    while m1 and m2:
      if m1[0] < m2[0]:
        m1 = m1[bisect_left(m1, m2[0]):]
      elif m2[0] < m1[0]:
        m2 = m2[bisect_left(m2, m1[0]):]
      else:
        new_data = [pos for pos in m1[0].data if (pos + self._delta in m2[0].data)]
        if new_data:
          matches.append(_MatchResult(key=m1[0].key, data=new_data))
        m1 = m1[1:]
        m2 = m2[1:]

    callback(_EvalResult(matches=matches, last_key=self._ComputeLastKey(results),
                         read_units=results[0].read_units + results[1].read_units))


class Parenthetical(_QueryNode):
  """This node encapsulates a child node and will be merged into
  _OpNodes as if it were a single value; This protects parenthesized
  trees from having their order adjusted.
  """
  def __init__(self, schema, child):
    # Collapse any nodes which have a missing left-hand node (this
    # can happen with a top-level positional intersection node that
    # has a place-holder term in the left-most position).
    if isinstance(child, PositionalIntersection) and child._left is None:
      child = child._right

    self._child = child
    self._precedence = 1000

  def PrintTree(self, level, param_dict):
    return self._child.PrintTree(level, param_dict)

  def Evaluate(self, client, callback, start_key, consistent_read, param_dict):
    self._child.Evaluate(client, callback, start_key, consistent_read, param_dict)


class PhraseNode(_QueryNode):
  """This node encapsulates a phrase, which may be a single term, or
  an arbitrarily complex subtree. For example, a phrase query with
  term expansions. The first pass through the parser merely sets the
  phrase on creation. However, when the tree is initialized, the
  phrase subtree is created.
  """
  def __init__(self, schema, table_name, column_name, phrase):
    """Convert the phrase into a query string using the appropriate
    indexer object (found via table:column in schema). This query
    string is passed to the phrase parser, and the new query subtree
    is set as the child of this PhraseNode.
    """
    self._precedence = 1000

    try:
      self.schema = schema
      self.table = self.schema.GetTable(table_name)
      assert isinstance(self.table, IndexedTable), table_name
      column = self.table.GetColumn(column_name)
      assert column.indexer, column_name
      self.column = column
      self.phrase = phrase
      self.child_parser = _PhraseParser(self.schema, self.table, column)
    except:
      logging.exception('phrase \'%s\'' % phrase)
      raise

  def _CreateChildNode(self, param_dict):
    if isinstance(self.phrase, Parameter):
      phrase = self.phrase.Resolve(param_dict)
    else:
      assert isinstance(self.phrase, basestring)
      phrase = self.phrase
    phrase_query_str = self.column.indexer.GetQueryString(self.column, phrase)
    match = _QUOTED_TOKEN_RE.match(phrase_query_str)
    if match is not None:
      # Fast path: it's one token, so create the IndexTermNode directly.
      return IndexTermNode(self.schema, self.table, self.column, match.group(1))
    else:
      # Slow path: run the real query parser to make sure we tokenize more complex queries correctly.
      return self.child_parser.Run(phrase_query_str)

  def PrintTree(self, level, param_dict):
    child = self._CreateChildNode(param_dict)
    return child.PrintTree(level, param_dict)

  def Evaluate(self, client, callback, start_key, consistent_read, param_dict):
    child = self._CreateChildNode(param_dict)
    child.Evaluate(client, callback, start_key, consistent_read, param_dict)


class IndexTermNode(_QueryNode):
  """Accesses the posting list for the indexed term from table:column.
  The term itself is indexed according to the rules of the column
  indexer and the posting lists for each emitted term are queried.
  """
  def __init__(self, schema, table, column, index_term):
    self._table = table
    self._column = column
    self._index_term = escape.utf8(index_term)
    self._precedence = 1000
    self._start_key = None
    self._last_key = None
    self._matches = None

  def PrintTree(self, level, param_dict):
    return self._index_term

  def Evaluate(self, client, callback, start_key, consistent_read, param_dict):
    """Queries the database for keys beginning with start_key, with a
    limit defined in the table schema. Consistent reads are disabled
    as they're unlikely to make a difference in search results (and
    are half as expensive in the DynamoDB cost model).
    """
    def _OnQuery(result):
      self._start_key = start_key
      self._last_key = result.last_key.range_key if result.last_key is not None else None
      self._matches = [_MatchResult(
          key=item['k'], data=self._Unpack(item.get('d', None))) for item in result.items]
      callback(_EvalResult(matches=self._matches, last_key=self._last_key,
                           read_units=result.read_units))

    if self._start_key and self._start_key <= start_key and \
          self._last_key and self._last_key > start_key:
      self._start_key = start_key
      self._matches = self._matches[
        bisect_right(self._matches, _MatchResult(key=start_key, data=None)):]
      callback(_EvalResult(matches=self._matches, last_key=self._last_key,
                           read_units=0))
    else:
      excl_start_key = db_client.DBKey(self._index_term, start_key) if start_key is not None else None
      client.Query(table=vf_schema.INDEX, hash_key=self._index_term,
                   range_operator=None, attributes=None, callback=_OnQuery,
                   limit=vf_schema.SCHEMA.GetTable(vf_schema.INDEX).scan_limit,
                   consistent_read=consistent_read, excl_start_key=excl_start_key)

  def _Unpack(self, data):
    return self._column.indexer.UnpackFreight(self._column, data)


class Parameter(object):
  def __init__(self, param_name):
    self.param_name = param_name

  def __str__(self):
    return '{%s}' % self.param_name

  def Resolve(self, param_dict):
    param_value = None if param_dict is None else param_dict.get(self.param_name, None)
    assert param_value is not None, 'No value for query parameter: %s' % self.param_name
    return param_value


class _QueryParser(object):
  def __init__(self, schema, parse_phrase_func=None):
    self._schema = schema

    if not parse_phrase_func:
      parse_phrase_func = self._ParsePhrase

    self._op_classes = {'|': Union, '-': Difference,
                        '&': Intersection, '+': PositionalIntersection}
    self._operator = p(lexeme, p(one_of, u''.join(self._op_classes.keys())))
    token_char = p(one_of, letters + digits + ':_')
    self._token = as_string(p(many1, token_char))
    self._phrase = p(choice, quoted, self._token)
    self._param_parser = p(choice, self._ParseParam, quoted, self._token)
    self._term_parser = p(choice, self._ParseParenthetical, parse_phrase_func)
    self._expr_parser = p(choice, self._ParseOp, self._term_parser)

  def Run(self, query_str):
    """Runs the parser on the provided query expression and returns
    the resulting query tree.
    """
    # Convert query_str to Unicode since picoparser expects Unicode for non-ASCII characters.
    query_tree, _ = run_text_parser(self._expr_parser, escape.to_unicode(query_str))
    return query_tree

  @tri
  def _ParseOp(self):
    """Consumes one operation, defined by left term and right
    expression, which may be either another term or another ParseOp().
    """
    left = self._term_parser()
    op = self._operator()
    commit()
    right = self._expr_parser()
    whitespace()
    node = self._op_classes[op](self._schema, left)
    return node.Merge(right)

  @tri
  def _ParseParenthetical(self):
    """Consumes parenthetical expression."""
    whitespace()
    one_of('(')
    commit()
    whitespace()
    node = self._expr_parser()
    whitespace()
    one_of(')')
    whitespace()
    return Parenthetical(self._schema, node)

  @tri
  def _ParseParam(self):
    """Consumes parameter keys for lookup in a parameter dictionary passed in with the query.
    Parameter keys may consist of letters, digits and underscores (_).
    Returns the value that the parameter key maps to.
    """
    one_of('{')
    param_name = ''.join(many_until1(p(one_of, letters + digits + '_'), p(one_of, '}'))[0])
    return Parameter(param_name)

  @tri
  def _ParsePhrase(self):
    """Consumes a key range specification of the form <table>.<column>=<maybe
    quoted value>.
    """
    whitespace()
    table = self._token().lower()
    one_of('.')
    commit()
    column = self._token().lower()
    whitespace()
    one_of('=')
    whitespace()
    phrase = self._param_parser()
    node = PhraseNode(self._schema, table, column, phrase)
    whitespace()
    return node


class _PhraseParser(_QueryParser):
  def __init__(self, schema, table, column):
    super(_PhraseParser, self).__init__(schema, self._ParseIndexTerm)
    self._table = table
    self._column = column

  def _ParseIndexTerm(self):
    """Consumes an index term. If '_', creates a place-holder node
    (None); otherwise, creates an IndexTermNode.
    """
    whitespace()
    index_term = self._phrase()
    if index_term == '_':
      node = None
    else:
      node = IndexTermNode(
        self._schema, self._table, self._column, index_term)
    whitespace()
    return node


class Query(object):
  """Parses a query into a hierarchical tree of set operations
  in the context of the provided data schema.
  """
  def __init__(self, schema, query_str):
    """Parses query_str into a query node tree."""
    self._query_str = query_str
    self._query_tree = _QueryParser(schema).Run(query_str)

  def PrintTree(self, param_dict):
    print self._query_str, param_dict
    print self._query_tree.PrintTree(0, param_dict)

  def Evaluate(self, client, callback, limit=50, start_key=None, end_key=None,
               consistent_read=False, param_dict=None):
    """Evaluates the query tree according to the provided db
    client. 'callback' is invoked with the query results.

    Returns keys matching the query expression, up to the limit.
    """
    def _OnEvaluate(results, read_units, eval_result):
      results += [mr.key for mr in eval_result.matches if (not end_key or mr.key < end_key)]
      read_units += eval_result.read_units
      reached_end_key = end_key is not None and eval_result.last_key >= end_key
      reached_limit = limit is not None and len(results) >= limit
      if eval_result.last_key is None or reached_end_key or reached_limit:
        logging.debug('query required %d read units' % read_units)
        results = results[:limit]
        callback(results)
      else:
        logging.debug('query under limit at key %s (%d < %s), '
                      '%d read units; extending query' %
                      (repr(eval_result.last_key), len(results),
                       limit if limit is not None else 'all', read_units))
        self._query_tree.Evaluate(client, partial(_OnEvaluate, results, read_units),
                                  eval_result.last_key, consistent_read, param_dict)

    results = []
    self._query_tree.Evaluate(client, partial(_OnEvaluate, results, 0),
                              start_key, consistent_read, param_dict)


def CompileQuery(schema, bound_query_str):
  """Returns a bound query (a (Query, param_dict) pair) for the given schema and query expression.

  bound_query_str can be either a query string, or a (query_str, param_dict) pair.
  (This interface is used for consistency with an older interface).

  Usage:
    query, param_dict = query_parser.CompileQuery(schema, (query_str, param_dict))
    query.Evaluate(..., param_dict)
  """
  if isinstance(bound_query_str, tuple):
    query_str, param_dict = bound_query_str
  else:
    query_str = bound_query_str
    param_dict = None
  query = _query_cache.Get((schema, query_str), lambda: Query(schema, query_str))
  return query, param_dict
