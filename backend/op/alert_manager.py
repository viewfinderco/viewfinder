# -*- coding: utf-8 -*-
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Viewfinder alert manager.

Composes and sends mobile device push notifications, emails, and SMS messages that notify end
users of interesting or notable activity that affects them. These alerts can be controlled by
the receiving user, who can limit or disable them. Only certain operations trigger the alerts,
such as starting a new conversation or posting a comment.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import json
import logging

from datetime import date
from tornado import escape, gen, options
from urllib import urlencode
from viewfinder.backend.base import util
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.comment import Comment
from viewfinder.backend.db.device import Device
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.settings import AccountSettings
from viewfinder.backend.db.user import User
from viewfinder.backend.resources.resources_mgr import ResourcesManager
from viewfinder.backend.services.email_mgr import EmailManager
from viewfinder.backend.services.push_notification import PushNotification
from viewfinder.backend.services.sms_mgr import SMSManager
from viewfinder.backend.services import sms_util


class AlertManager(object):
  """Viewfinder alert manager."""
  _EMAIL_PHOTO_COUNT = 3
  """Maximum number of photos in an alert email."""

  _MAX_COVER_PHOTO_DIM = 416
  """Number of pixels in the cover photo's maximum dimension."""

  _SMS_ALERT_LIMIT = 3
  """Maximum number of SMS alerts that will be sent if the user does not click on links. Be
  careful about changing this as it can result in the user getting multiple warnings and/or
  having their messages stop without a warning.
  """

  @classmethod
  @gen.coroutine
  def SendFollowerAlert(cls, client, user_id, badge, viewpoint, follower, settings, activity):
    """Sends an APNS and/or email alert to the given follower according to his alert settings."""
    # Only send add_followers alert to users who were added.
    if activity.name == 'add_followers':
      args_dict = json.loads(activity.json)
      if user_id not in args_dict['follower_ids']:
        return

    if follower.IsMuted():
      # User has muted this viewpoint, so don't send any alerts.
      return

    if settings.push_alerts is not None and settings.push_alerts != AccountSettings.PUSH_NONE:
      alert_text = yield AlertManager._FormatAlertText(client, viewpoint, activity)
      if alert_text is not None:
        # Only alert with sound if this is the first unread activity for the conversation.
        if follower.viewed_seq + 1 >= viewpoint.update_seq:
          sound = PushNotification.DEFAULT_SOUND
        else:
          sound = None

        viewpoint_id = viewpoint.viewpoint_id if viewpoint is not None else None
        yield AlertManager._SendDeviceAlert(client, user_id, viewpoint_id, badge, alert_text, sound=sound)

    if settings.email_alerts is not None and settings.email_alerts != AccountSettings.EMAIL_NONE:
      alert_email_args = yield AlertManager._FormatAlertEmail(client, user_id, viewpoint, activity)
      if alert_email_args is not None:
        # Possible failure of email alert should not propagate.
        try:
          yield gen.Task(EmailManager.Instance().SendEmail, description=activity.name, **alert_email_args)
        except:
          logging.exception('failed to send alert email user %d', user_id)

    if settings.sms_alerts is not None and settings.sms_alerts != AccountSettings.SMS_NONE:
      alert_sms_args = yield AlertManager._FormatAlertSMS(client, user_id, viewpoint, activity)
      if alert_sms_args is not None:
        # Don't keep sending SMS alerts if the user hasn't clicked previous links in a while.
        sms_count = settings.sms_count or 0
        if sms_count == AlertManager._SMS_ALERT_LIMIT:
          # Send SMS alert telling user that we won't send any more until they click link.
          text = alert_sms_args['text']
          alert_sms_args['text'] = 'You haven\'t viewed photos shared to you on Viewfinder. Do you want to ' \
                                   'continue receiving these links? If yes, click: %s' % text[text.rfind('https://'):]

        if sms_count <= AlertManager._SMS_ALERT_LIMIT:
          # Possible failure of SMS alert should not propagate.
          try:
            yield gen.Task(SMSManager.Instance().SendSMS, description=activity.name, **alert_sms_args)
          except:
            logging.exception('failed to send alert SMS message user %d', user_id)

        # Increment the SMS alert count.
        settings.sms_count = sms_count + 1
        yield gen.Task(settings.Update, client)

  @classmethod
  @gen.coroutine
  def SendRegisterAlert(cls, client, register_user_id, target_user_id, target_settings):
    """Sends alert to the specified target user, notifying him that one of his contacts has
    registered for Viewfinder.
    """
    if target_settings.push_alerts is not None and target_settings.push_alerts != AccountSettings.PUSH_NONE:
      if register_user_id != target_user_id:
        target_name = yield AlertManager._GetNameFromUserId(client, register_user_id, prefer_given_name=False)
        alert_text = '%s has joined Viewfinder' % target_name

        yield AlertManager._SendDeviceAlert(client,
                                            target_user_id,
                                            viewpoint_id=None,
                                            badge=None,
                                            alert_text=alert_text,
                                            sound=PushNotification.DEFAULT_SOUND)

  @classmethod
  @gen.coroutine
  def SendClearBadgesAlert(cls, client, user_id, exclude_device_id=None):
    """Sends alert which will clear the specified user's badge."""
    yield AlertManager._SendDeviceAlert(client,
                                        user_id,
                                        viewpoint_id=None,
                                        badge=0,
                                        alert_text=None,
                                        exclude_device_id=exclude_device_id)

  @classmethod
  @gen.coroutine
  def _SendDeviceAlert(cls, client, user_id, viewpoint_id, badge, alert_text, exclude_device_id=None, sound=None):
    """Sends an APNS alert to the devices of the user who owns this NotificationManager. If
    "exclude_device_id" is not None, skip that device. The alert will embed the viewpoint_id
    as an extra "v" attribute if it's specified in the NotificationManager. This lets clients
    determine which viewpoint triggered the alert.
    """
    # Possible failure of push notification should not propagate.
    try:
      # Alert_text can be None, which will still result in update of badge.
      extra = {'v': viewpoint_id} if viewpoint_id is not None and alert_text is not None else None
      yield gen.Task(Device.PushNotification,
                     client,
                     user_id,
                     alert_text,
                     badge,
                     exclude_device_id=exclude_device_id,
                     extra=extra,
                     sound=sound)
    except:
      logging.exception('failed to push notification to user %d', user_id)

  @classmethod
  @gen.coroutine
  def _FormatAlertText(cls, client, viewpoint, activity):
    """Gets the text that will be pushed to the devices of users who follow the activity's
    viewpoint. This is async because some of the activity's identifiers may need to be resolved
    to actual objects in the database in order to construct the text.
    """
    if activity.name == 'add_followers':
      alert_text = yield AlertManager._FormatAddFollowersText(client, viewpoint, activity)
    elif activity.name == 'post_comment':
      alert_text = yield AlertManager._FormatPostCommentText(client, viewpoint, activity)
    elif activity.name == 'share_existing':
      alert_text = yield AlertManager._FormatShareExistingText(client, viewpoint, activity)
    elif activity.name == 'share_new':
      alert_text = yield AlertManager._FormatShareNewText(client, viewpoint, activity)
    else:
      alert_text = None

    raise gen.Return(alert_text)

  @classmethod
  @gen.coroutine
  def _FormatAlertEmail(cls, client, recipient_id, viewpoint, activity):
    """Gets the arguments to the email that will be sent to web-only customers who follow the
    activity's viewpoint.
    """
    if activity.name == 'share_new' or activity.name == 'add_followers':
      email_args = yield AlertManager._FormatConversationEmail(client, recipient_id, viewpoint, activity)
    else:
      email_args = None

    raise gen.Return(email_args)

  @classmethod
  @gen.coroutine
  def _FormatAlertSMS(cls, client, recipient_id, viewpoint, activity):
    """Gets the arguments to the SMS that will be sent to web-only customers who follow the
    activity's viewpoint.
    """
    if activity.name == 'share_new' or activity.name == 'add_followers':
      sms_args = yield AlertManager._FormatConversationSMS(client, recipient_id, viewpoint, activity)
    else:
      sms_args = None

    raise gen.Return(sms_args)

  @classmethod
  @gen.coroutine
  def _FormatAddFollowersText(cls, client, viewpoint, activity):
    """Constructs the alert text for an "add_followers" operation, similar to this:
         Andy added you to a conversation: "And Then There Was Brick"
    """
    sharer_name = yield AlertManager._GetNameFromUserId(client, activity.user_id)
    raise gen.Return('%s added you to a conversation%s' % (sharer_name, AlertManager._GetViewpointTitle(viewpoint)))

  @classmethod
  @gen.coroutine
  def _FormatPostCommentText(cls, client, viewpoint, activity):
    """Constructs the alert text for a "post_comment" operation, similar to this:
         Andy: What a great experience
    """
    # Query to get the name of the comment poster and the text of the comment.
    args_dict = json.loads(activity.json)
    comment = yield gen.Task(Comment.Query, client, viewpoint.viewpoint_id, args_dict['comment_id'], None)

    sharer_name = yield AlertManager._GetNameFromUserId(client, activity.user_id)
    raise gen.Return('%s: %s' % (sharer_name, comment.message))

  @classmethod
  @gen.coroutine
  def _FormatShareExistingText(cls, client, viewpoint, activity):
    """Constructs the alert text for a "share_existing" operation, similar to this:
         Andy shared 5 photos to: "And Then There Was Brick"
         Andy shared 5 photos
    """
    sharer_name = yield AlertManager._GetNameFromUserId(client, activity.user_id)
    episode_dates, num_shares = AlertManager._GetShareInfo(activity)
    viewpoint_title = AlertManager._GetViewpointTitle(viewpoint)
    if viewpoint_title:
      raise gen.Return('%s shared %d photo%s to%s' % (sharer_name,
                                                      num_shares,
                                                      util.Pluralize(num_shares),
                                                      viewpoint_title))
    else:
      raise gen.Return('%s shared %d photo%s' % (sharer_name,
                                                 num_shares,
                                                 util.Pluralize(num_shares)))

  @classmethod
  @gen.coroutine
  def _FormatShareNewText(cls, client, viewpoint, activity):
    """Constructs the alert text for a "share_new" operation, similar to this:
         Andy started a conversation: "And Then There Was Brick"
         Andy shared 5 photos
    """
    sharer_name = yield AlertManager._GetNameFromUserId(client, activity.user_id)
    episode_dates, num_shares = AlertManager._GetShareInfo(activity)
    viewpoint_title = AlertManager._GetViewpointTitle(viewpoint)
    if viewpoint_title:
      raise gen.Return('%s started a conversation%s' % (sharer_name,
                                                        viewpoint_title))
    elif num_shares > 0:
      raise gen.Return('%s shared %d photo%s' % (sharer_name,
                                                 num_shares,
                                                 util.Pluralize(num_shares)))
    else:
      raise gen.Return('%s added you to a conversation' % sharer_name)

  @classmethod
  @gen.coroutine
  def _FormatConversationSMS(cls, client, recipient_id, viewpoint, activity):
    """Constructs an SMS message which alerts the recipient that they have access to a new
    conversation, either due to a share_new operation, or to an add_followers operation.
    The SMS message includes a clickable link to the conversation on the web site.
    """
    # Get phone number of recipient.
    recipient_user = yield gen.Task(User.Query, client, recipient_id, None)
    if recipient_user.phone is None:
      # No phone number associated with user, so can't send SMS.
      raise gen.Return(None)

    identity_key = 'Phone:%s' % recipient_user.phone

    # Get name of sharer. Try to use only the sharer's given name if the recipient is already registered.
    sharer = yield gen.Task(User.Query, client, activity.user_id, None)
    sharer_name = AlertManager._GetNameFromUser(sharer, prefer_given_name=recipient_user.IsRegistered())

    # Create ShortURL that sets prospective user cookie and then redirects to the conversation.
    viewpoint_url = yield AlertManager._CreateViewpointURL(client,
                                                           recipient_user,
                                                           identity_key,
                                                           viewpoint,
                                                           use_short_domain=True)

    # Create list of SMS message strings, in order of decreasing length. 
    sms_list = []

    if viewpoint.title:
      # 1. Use title, with photos.
      if viewpoint.cover_photo:
        text = '%s shared photos titled "%s". See them on Viewfinder: %s'
        sms_list.append(text % (sharer_name, viewpoint.title, viewpoint_url))

      # 2. Use title, without photos.
      text = '%s shared "%s" with you. See it on Viewfinder: %s'
      sms_list.append(text % (sharer_name, viewpoint.title, viewpoint_url))

      # 3. Use title, shortest form.
      text = '%s shared "%s" on Viewfinder: %s'
      sms_list.append(text % (sharer_name, viewpoint.title, viewpoint_url))

      # 4. Use title, shortest form, with given name.
      if sharer.given_name:
        sms_list.append(text % (sharer.given_name, viewpoint.title, viewpoint_url))

    if viewpoint.cover_photo:
      # 5. Omit title, with photos.
      text = '%s shared photos on Viewfinder: %s'
      sms_list.append(text % (sharer_name, viewpoint_url))

    # 6. Omit title, without photos.
    text = '%s shared on Viewfinder: %s'
    sms_list.append(text % (sharer_name, viewpoint_url))

    # 7. Use only sharer's given name.
    if sharer.given_name:
      sms_list.append(text % (sharer.given_name, viewpoint_url))

    # For registered user, don't need to mention Viewfinder.
    if recipient_user.IsRegistered():
      if viewpoint.cover_photo:
        # 8. No mention of Viewfinder, with photos.
        text = '%s shared photos: %s'
        sms_list.append(text % (sharer_name, viewpoint_url))

      # 9. No mention of Viewfinder, without photos.
      text = '%s shared: %s'
      sms_list.append(text % (sharer_name, viewpoint_url))

    # 10. Use truncated sharer name.
    remaining = sms_util.MAX_UTF16_CHARS - len(text % ('', viewpoint_url))
    name = escape.to_unicode(sharer_name)[:remaining]
    sms_list.append(text % (name, viewpoint_url))

    # Now loop through the possible SMS message string and find the first that will fit in
    # a single SMS message.
    for text in sms_list:
      # Work around Twilio bug showing Greek chars in GSM encoding. Force Unicode by replacing
      # the last space char with a tab (the one just before the web link).
      if sms_util.ForceUnicode(text):
        parts = text.rsplit(' ', 1)
        text = '\t'.join(parts)

      if sms_util.IsOneSMSMessage(text):
        break

    assert text, text

    raise gen.Return({'number': recipient_user.phone,
                      'text': text})

  @classmethod
  @gen.coroutine
  def _FormatConversationEmail(cls, client, recipient_id, viewpoint, activity):
    """Constructs an email which alerts the recipient that they have access to a new
    conversation, either due to a share_new operation, or to an add_followers operation.
    The email includes a clickable link to the conversation on the web site.
    """
    from viewfinder.backend.db.identity import Identity
    from viewfinder.backend.db.photo import Photo
    from viewfinder.backend.db.user import User

    # Get email address of recipient.
    recipient_user = yield gen.Task(User.Query, client, recipient_id, None)
    if recipient_user.email is None:
      # No email address associated with user, so can't send email.
      raise gen.Return(None)

    identity_key = 'Email:%s' % recipient_user.email

    # Create ShortURL that sets prospective user cookie and then redirects to the conversation.
    viewpoint_url = yield AlertManager._CreateViewpointURL(client, recipient_user, identity_key, viewpoint)

    sharer = yield gen.Task(User.Query, client, activity.user_id, None)
    sharer_name = AlertManager._GetNameFromUser(sharer, prefer_given_name=False)

    # Create the cover photo ShortURL by appending a "next" query parameter to the viewpoint ShortURL.
    cover_photo_url = None
    cover_photo_height = None
    cover_photo_width = None
    if viewpoint.cover_photo != None:
      next_url = '/episodes/%s/photos/%s.f' % (viewpoint.cover_photo['episode_id'], viewpoint.cover_photo['photo_id'])
      cover_photo_url = "%s?%s" % (viewpoint_url, urlencode(dict(next=next_url)))

      photo = yield gen.Task(Photo.Query, client, viewpoint.cover_photo['photo_id'], None)

      if photo.aspect_ratio < 1:
        cover_photo_height = AlertManager._MAX_COVER_PHOTO_DIM
        cover_photo_width = int(AlertManager._MAX_COVER_PHOTO_DIM * photo.aspect_ratio)
      else:
        cover_photo_width = AlertManager._MAX_COVER_PHOTO_DIM
        cover_photo_height = int(AlertManager._MAX_COVER_PHOTO_DIM / photo.aspect_ratio)

    email_args = {'from': EmailManager.Instance().GetInfoAddress(),
                  'to': recipient_user.email,
                  'subject': '%s added you to a conversation' % sharer_name}
    util.SetIfNotEmpty(email_args, 'toname', recipient_user.name)
    if sharer_name:
      email_args['fromname'] = '%s via Viewfinder' % sharer_name

    # Create the unsubscribe URL.
    unsubscribe_cookie = User.CreateUnsubscribeCookie(recipient_id, AccountSettings.EMAIL_ALERTS)
    unsubscribe_url = 'https://%s/unsubscribe?%s' % (options.options.domain,
                                                     urlencode(dict(cookie=unsubscribe_cookie)))

    # Set viewpoint title.
    viewpoint_title = viewpoint.title if viewpoint is not None else None

    fmt_args = {'cover_photo_url': cover_photo_url,
                'cover_photo_height': cover_photo_height,
                'cover_photo_width': cover_photo_width,
                'viewpoint_url': viewpoint_url,
                'unsubscribe_url': unsubscribe_url,
                'sharer_name': sharer_name,
                'viewpoint_title': viewpoint_title,
                'toname': recipient_user.name}

    resources_mgr = ResourcesManager.Instance()

    email_args['html'] = escape.squeeze(resources_mgr.GenerateTemplate('alert_conv_base.email',
                                                                       is_html=True,
                                                                       **fmt_args))
    email_args['text'] = resources_mgr.GenerateTemplate('alert_conv_base.email',
                                                        is_html=False,
                                                        **fmt_args)

    raise gen.Return(email_args)

  @classmethod
  def _GetNameFromUser(cls, user, prefer_given_name=True):
    """Gets the name of a user. Prefers the given name, then the full name, then the email, then
    just "A friend". If "prefer_given_name" is false, then don't use the given name.
    """
    if user.given_name and prefer_given_name:
      return user.given_name
    elif user.name:
      return user.name
    elif user.email:
      return user.email
    else:
      return 'A friend'

  @classmethod
  @gen.coroutine
  def _GetNameFromUserId(cls, client, user_id, prefer_given_name=True):
    """Looks up a user by id and returns the name of the user by calling _GetNameFromUser."""
    from viewfinder.backend.db.user import User

    user = yield gen.Task(User.Query, client, user_id, None)
    raise gen.Return(AlertManager._GetNameFromUser(user, prefer_given_name))

  @classmethod
  def _GetViewpointTitle(cls, viewpoint):
    """Returns the title of the viewpoint, or the empty string if no title exists."""
    viewpoint_title = viewpoint.title if viewpoint is not None else None
    if viewpoint_title is not None:
      return ': "%s"' % viewpoint_title
    return ''

  @classmethod
  def _GetShareInfo(cls, activity):
    """Returns a tuple with information about a "share_existing" or "share_new" operation:
         episode_dates: List of timestamps for each episode in the share.
         num_shares: Total count of photos shared.
    """
    episode_dates = []
    num_shares = 0

    args_dict = json.loads(activity.json)
    for ep_dict in args_dict['episodes']:
      # Extract timestamps from episode id so that we don't need to query for episode object.
      ts, dev_id, uniquifier = Episode.DeconstructEpisodeId(ep_dict['episode_id'])
      episode_dates.append(date.fromtimestamp(ts))

      num_shares += len(ep_dict['photo_ids'])

    return (episode_dates, num_shares)

  @classmethod
  @gen.coroutine
  def _CreateViewpointURL(cls, client, recipient_user, identity_key, viewpoint, use_short_domain=False):
    """Creates a Short URL which links to a conversation on the website.

    If "use_short_domain" is true, then return a URL that uses the short domain, along with
    a shorter group_id prefix that will get re-mapped by ShortDomainRedirectHandler.
    """
    # Create ShortURL that sets prospective user cookie and then redirects to the conversation.
    short_url = yield Identity.CreateInvitationURL(client,
                                                   recipient_user.user_id,
                                                   identity_key,
                                                   viewpoint.viewpoint_id,
                                                   default_url='/view#conv/%s' % viewpoint.viewpoint_id)

    # ShortURL's can use either the regular domain or the short domain. For SMS messages, we
    # typically use the short domain. For email, we typically use the regular domain. 
    if use_short_domain:
      assert short_url.group_id.startswith('pr/'), short_url
      raise gen.Return('https://%s/p%s%s' %
                       (options.options.short_domain, short_url.group_id[3:], short_url.random_key))

    raise gen.Return('https://%s/%s%s' % (options.options.domain, short_url.group_id, short_url.random_key))
