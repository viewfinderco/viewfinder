# -*- coding: utf-8 -*-
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""SMS utilities.

Helper methods used when sending SMS messages.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import re

from tornado import escape


# Regular expression used to identify valid GSM characters, which is the 7-bit character set
# that is widely supported by SMS systems across the world (i.e. *not* ASCII):
#   https://en.wikipedia.org/wiki/GSM_03.38
_good_gsm_chars = u'@£$¥èéùìòÇ\nØø\rÅå_ÆæßÉ !"#%&\'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà'
assert len(_good_gsm_chars) == 116
_gsm_re = re.compile(u'^[%s]*$' % re.escape(_good_gsm_chars))

# Greek capital letters contained in the GSM character set, and the currency symbol don't get
# sent properly in the GSM encoding (they get mapped into other chars by some intermediary).
_bad_gsm_chars = u'¤ΔΦΓΛΩΠΨΣΘΞ'
assert len(escape.to_unicode(_bad_gsm_chars)) == 11
_force_unicode_re = re.compile(u'^[%s%s]*$' % (re.escape(_bad_gsm_chars), re.escape(_good_gsm_chars)))


# Maximum number of GSM encoded chars that Twilio can send.
MAX_GSM_CHARS = 160

# Maximum number of UTF-16 encoded chars that Twilio can send. The SMS spec really uses the
# UCS-2 encoding, but many/most devices allow UTF-16, which allows non-BMP chars to be used
# (such as Emoji).
MAX_UTF16_CHARS = 70


def ForceUnicode(value):
  """Returns true if the value contains only GSM chars, but also contains at least one
  problematic GSM char, such as a Greek capital letter. In this case, the caller should
  force the UCS-2 SMS encoding so that GSM will not be attempted.
  """
  value = escape.to_unicode(value)
  return _force_unicode_re.search(value) and not _gsm_re.search(value)


def IsOneSMSMessage(value):
  """Returns true if the value can be sent in a single SMS message. If the value contains
  only GSM chars, then it can be up to 160 chars. Otherwise, it must be sent as Unicode and
  can only be up to 70 chars.
  """
  value = escape.to_unicode(value)
  utf16_count = len(value.encode('utf-16-be')) / 2
  if _gsm_re.search(value):
    return utf16_count <= MAX_GSM_CHARS

  return utf16_count <= MAX_UTF16_CHARS
