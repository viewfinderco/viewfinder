# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Utilities module for use from db/tools.

  - AttrParser: parser for attribute key/value pairs
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging
import signal

from picoparse import one_of, choice, many, tri, commit, p
from picoparse.text import run_text_parser, as_string, quoted
from string import digits, letters
from tornado import escape, ioloop, options
from viewfinder.backend.db import db_client


class AttrParser(object):
  """A pico parser to handle attributes specified on the command line.
  Builds a map
  """
  def __init__(self, table, raw=False):
    self._table = table
    self._raw = raw
    self._updates = dict()
    token_char = p(one_of, letters + digits + '.-_')
    self._token = as_string(p(many, token_char))
    self._phrase = p(choice, quoted, self._token)
    self._expr_parser = p(many, p(choice, p(one_of, ','), self._ParsePhrase))

  def Run(self, attributes):
    """Runs the parser on the provided comma-separated string of attributes.
    """
    # Convert query_expr to Unicode since picoparser expects Unicode for non-ASCII characters.
    _ = run_text_parser(self._expr_parser, escape.to_unicode(attributes))
    return self._updates

  @tri
  def _ParsePhrase(self):
    """Reads one attribute col_name=value. Creates a DB update
    in self._updates.
    """
    col_name = self._token().lower()
    col_def = self._table.GetColumn(col_name)
    one_of('=')
    commit()
    phrase = self._phrase()
    if phrase:
      value = eval(phrase)
      if col_def.value_type == 'N':
        value = int(value)
      if self._raw:
        self._updates[col_def.key] = db_client.UpdateAttr(value, 'PUT')
      else:
        self._updates[col_name] = value
    else:
      if self._raw:
        self._updates[col_def.key] = db_client.UpdateAttr(None, 'DELETE')
      else:
        self._updates[col_name] = None
    return None
