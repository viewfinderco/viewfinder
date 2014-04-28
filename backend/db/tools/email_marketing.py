# Copyright 2013 Viewfinder Inc. All Rights Reserved.

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import sys

from functools import partial
from tornado import escape, gen
from tornado.options import options
from tornado.template import Template
from urllib import urlencode
from viewfinder.backend.base import main, util
from viewfinder.backend.db.db_client import DBClient, DBKey
from viewfinder.backend.db.settings import AccountSettings
from viewfinder.backend.db.user import User
from viewfinder.backend.services.email_mgr import EmailManager, SendGridEmailManager
from viewfinder.backend.services.sms_mgr import SMSManager, TwilioSMSManager

options.define('email_template', default=None, type=str,
               help='name of the .email template file to use')
options.define('email_subject', default='New Viewfinder Features', type=str,
               help='subject to relay with email message')
options.define('sms_template', default=None, type=str,
               help='name of the .sms template file to use')
options.define('min_user_id', default=11, type=int,
               help='only users with ids >= this id will be sent email/SMS (-1 for no min)')
options.define('max_user_id', default=11, type=int,
               help='only users with ids <= this id will be sent email/SMS (-1 for no max)')
options.define('honor_allow_marketing', default=True, type=bool,
               help='do not send the email/SMS if the user has turned off marketing emails')
options.define('test_mode', default=True, type=bool,
               help='do not send the email/SMS; print the first email/SMS that would have been sent')

_is_first_email = True
_is_first_sms = True


@gen.coroutine
def GetRegisteredUsers(client, last_user_id):
  """Get next batch of users that are registered, and that have a primary email or phone."""
  if options.min_user_id == options.max_user_id and options.min_user_id != -1:
    # Shortcut for single user.
    if last_user_id is None:
      result = [(yield gen.Task(User.Query, client, options.min_user_id, None))]
    else:
      result = []
  else:
    start_key = DBKey(last_user_id, None) if last_user_id is not None else None
    result = (yield gen.Task(User.Scan, client, None, excl_start_key=start_key))[0]

  users = [user for user in result if user.IsRegistered() and not user.IsTerminated() and (user.email or user.phone)]
  raise gen.Return(users)


@gen.coroutine
def SendEmailToUser(template, user):
  assert user.email is not None, user

  unsubscribe_cookie = User.CreateUnsubscribeCookie(user.user_id, AccountSettings.MARKETING)
  unsubscribe_url = 'https://%s/unsubscribe?%s' % (options.domain,
                                                   urlencode(dict(cookie=unsubscribe_cookie)))

  # Create arguments for the email template.
  fmt_args = {'first_name': user.given_name,
              'unsubscribe_url': unsubscribe_url}

  # Create arguments for the email.
  args = {'from': EmailManager.Instance().GetInfoAddress(),
          'fromname': 'Viewfinder',
          'to': user.email,
          'subject': options.email_subject}
  util.SetIfNotNone(args, 'toname', user.name)

  args['html'] = template.generate(is_html=True, **fmt_args)
  args['text'] = template.generate(is_html=False, **fmt_args)

  print 'Sending marketing email to %s (%s) (#%d)' % (user.email, user.name, user.user_id)

  if options.test_mode:
    global _is_first_email
    if _is_first_email:
      print args['html']
      _is_first_email = False
  else:
    # Remove extra whitespace in the HTML (seems to help it avoid Gmail spam filter).
    args['html'] = escape.squeeze(args['html'])

    yield gen.Task(EmailManager.Instance().SendEmail, description='marketing email', **args)


@gen.coroutine
def SendSMSToUser(template, user):
  assert user.phone is not None, user

  # Create arguments for the SMS template.
  fmt_args = {'first_name': user.given_name}

  # Create arguments for the SMS.
  args = {'number': user.phone,
          'text': template.generate(is_html=False, **fmt_args)}

  print 'Sending marketing SMS to %s (%s) (#%d)' % (user.phone, user.name, user.user_id)

  if options.test_mode:
    global _is_first_sms
    if _is_first_sms:
      print args['text']
      _is_first_sms = False
  else:
    yield gen.Task(SMSManager.Instance().SendSMS, description='marketing SMS', **args)


@gen.engine
def Run(callback):
  assert options.email_template, '--email_template must be set'

  EmailManager.SetInstance(SendGridEmailManager())
  SMSManager.SetInstance(TwilioSMSManager())

  # Load the email template.
  f = open(options.email_template, "r")
  email_template = Template(f.read())
  f.close()

  # Load the SMS template.
  if options.sms_template:
    f = open(options.sms_template, "r")
    sms_template = Template(f.read())
    f.close()

  sms_warning = False
  client = DBClient.Instance()
  last_user_id = None
  count = 0
  while True:
    users = yield GetRegisteredUsers(client, last_user_id)
    if not users:
      break

    count += len(users)
    print 'Scanned %d users...' % count
    for user in users:
      last_user_id = user.user_id
      if options.min_user_id != -1 and user.user_id < options.min_user_id:
        continue

      if options.max_user_id != -1 and user.user_id > options.max_user_id:
        continue

      # Only send to users which allow marketing communication to them.
      if options.honor_allow_marketing:
        settings = yield gen.Task(AccountSettings.QueryByUser, client, user.user_id, None)
        if not settings.AllowMarketing():
          continue

      if user.email:
        yield SendEmailToUser(email_template, user)
      elif user.phone:
        if not options.sms_template:
          if not sms_warning:
            print 'WARNING: no SMS template specified and phone-only accounts encountered; skipping...'
            sms_warning = True
        else:
          yield SendSMSToUser(sms_template, user)

  callback()

if __name__ == '__main__':
  sys.exit(main.InitAndRun(Run))
