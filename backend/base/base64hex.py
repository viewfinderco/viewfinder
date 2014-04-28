# Copyright 2012 Viewfinder Inc. All Rights Reserved.
"""Order-preserving variant of base64.

Uses the URL-safe 64 letter alphabet [0-9A-Za-z-_] to base-64
encode/decode binary strings. However, the values assigned to
each alphanumeric character properly preserve the sort ordering
of the original byte strings.

Based on the "Base 32 Encoding with Extended Hex Alphabet", as
described in RFC 4648, which preserves the bitwise sort order of
the original binary string.

http://tools.ietf.org/html/rfc4648

  B64HexEncode: encodes bytes to b64 hex encoding
  B64HexDecode: decodes bytes from b64 hex encoding
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'ben@emailscrubbed.com (Ben Darnell)']

import base64
import re
import string
from tornado.escape import utf8

_std_alphabet = string.uppercase + string.lowercase + string.digits + '+/'
_b64hex_alphabet = '-' + string.digits + string.uppercase + '_' + string.lowercase

assert sorted(_b64hex_alphabet) == list(_b64hex_alphabet)

_std_to_b64hex = string.maketrans(_std_alphabet, _b64hex_alphabet)
_b64hex_to_std = string.maketrans(_b64hex_alphabet, _std_alphabet)

_valid_char_re = re.compile('^[a-zA-Z0-9_-]*={0,3}$')

def B64HexEncode(s, padding=True):
  """Encode a string using Base64 with extended hex alphabet.

  s is the string to encode. The encoded string is returned.
  """
  encoded = base64.b64encode(s)
  translated = encoded.translate(_std_to_b64hex)
  if padding:
    return translated
  else:
    return translated.rstrip('=')

_PAD_LEN = 4

def B64HexDecode(s, padding=True):
  """Decode a Base64 encoded string.

  The decoded string is returned. A TypeError is raised if s is
  incorrectly padded or if there are non-alphabet characters present
  in the string.
  """
  s = utf8(s)
  # In python2.7 b64decode doesn't do the validation the docs say it does
  # http://bugs.python.org/issue1466065
  if not _valid_char_re.match(s):
    raise TypeError("Invalid characters")
  pad_needed = len(s) % _PAD_LEN
  if pad_needed:
    if padding:
      raise TypeError("Invalid padding")
    else:
      s += '=' * pad_needed
  translated = s.translate(_b64hex_to_std)
  return base64.b64decode(translated)
