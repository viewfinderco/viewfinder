# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Query parser tests.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball),' \
             'mike@emailscrubbed.com (Mike Purtell)'

import unittest

from viewfinder.backend.db import query_parser, vf_schema

class QueryParserTestCase(unittest.TestCase):
  def TryQuery(self, query, param_dict=None):
    query = query_parser.Query(vf_schema.SCHEMA, query)
    query.PrintTree(param_dict)

  def testQueryParser(self):
    self.TryQuery('user.given_name=Spencer')
    self.TryQuery('user.given_name=Spencer & user.family_name=Kimball')
    self.TryQuery('user.given_name=Spencer & user.family_name=Kimball'
                  ' - user.email="spencer@example.dot.com"')
    self.TryQuery('photo.caption="a little bit of text a"')
    self.TryQuery('photo.caption="search this text but not that" - '
                  'photo.caption="but not this phrase"')

    # now, test that parameterized queries work.
    self.TryQuery('user.given_name={fn}', {'fn': 'Spencer'})
    self.TryQuery('user.given_name={fn} & user.family_name={ln}', {'fn': 'Spencer', 'ln': 'Kimball'})
    self.TryQuery('user.given_name={fn} & user.family_name={ln} - user.email={e}',
                  {'fn': 'Spencer', 'ln': 'Kimball', 'e': 'spencer@example.dot.com'})
    self.TryQuery('photo.caption={c}', {'c': 'a little bit of text a'})
    self.TryQuery('photo.caption={c1} - photo.caption={c2}',
                  {'c1': 'search this text but not that', 'c2': 'but not this phrase'})
