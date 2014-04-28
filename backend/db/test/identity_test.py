# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests for Identity.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

from viewfinder.backend.base.exceptions import InvalidRequestError
from viewfinder.backend.db.identity import Identity

from base_test import DBBaseTestCase

class IdentityTestCase(DBBaseTestCase):
  KEY = 'Local:test@example.com'

  def testPhoneNumbers(self):
    """Test validation of phone numbers."""
    # United States.
    self.assertEqual(Identity.CanonicalizePhone('+14251234567'), '+14251234567')

    # Malaysia.
    self.assertEqual(Identity.CanonicalizePhone('+60321345678'), '+60321345678')

    # Great Britain.
    self.assertEqual(Identity.CanonicalizePhone('+442083661177'), '+442083661177')

    # China.
    self.assertEqual(Identity.CanonicalizePhone('+861082301234'), '+861082301234')

    self.assertRaises(InvalidRequestError, Identity.CanonicalizePhone, None)
    self.assertRaises(InvalidRequestError, Identity.CanonicalizePhone, '')
    self.assertRaises(InvalidRequestError, Identity.CanonicalizePhone, '14251234567')
    self.assertRaises(InvalidRequestError, Identity.CanonicalizePhone, '+')
    self.assertRaises(InvalidRequestError, Identity.CanonicalizePhone, '+abc')

  def testRepr(self):
    """Test conversion of Identity objects to strings."""
    ident = Identity.CreateFromKeywords(key='Email:foo@example.com',
                                        access_token='access_token1',
                                        refresh_token='refresh_token1')
    self.assertIn('foo@example.com', repr(ident))
    self.assertIn('scrubbed', repr(ident))
    self.assertNotIn('access_token1', repr(ident))
    self.assertNotIn('refresh_token1', repr(ident))
