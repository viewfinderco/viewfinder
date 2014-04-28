// Copyright 2012 Viewfinder Inc. All Rights Reserved.

/**
 * @fileoverview Register for an invitation to the BETA.
 *
 * @author spencer@emailscrubbed.com (Spencer Kimball)
 */

viewfinder.invite = {};


/**
 * Slides the teaser invitation div into view if not yet visible.
 * Slides it out of view otherwise. Handles email text input
 * keypresses: return on empty email to exit, return on entered email
 * submits for beta registration.
 */
viewfinder.invite.registerForInvite = function() {
  var $invite = $('#teaser-invite');
  if ($invite.is(':visible')) {
    viewfinder.invite.closeInvite_(1);
  } else {
    $invite.slideDown(function() {
      var $email = $('#teaser-email')
      $email.focus();
      $email.on('keypress', function(e) {
        if (e.which == 13) {
          if ($email.val() == '') {
            viewfinder.invite.closeInvite_(1);
            return false;
          }
          $.ajax({
            url: '/register_beta',
            type: 'POST',
            processData: false,
            data: JSON.stringify({'email': $email.val()}),
            contentType: 'application/json; charset=UTF-8',
            dataType: 'json',
          }).done(function(data) {
            viewfinder.invite.setStatus_(data.error, data.message);
            if (!data.error) {
              viewfinder.invite.closeInvite_();
            }
          }).fail(function(jqXHR, textStatus) {
            viewfinder.invite.setStatus_(true, 'Unable to register for Beta; try again later.');
            viewfinder.invite.closeInvite_();
          });
          return false;
        }
      });
    });
  }
};

/**
 * Displays the status message either as an error or a status.
 */
viewfinder.invite.setStatus_ = function(error, status) {
  var $status_div;
  if (error) {
    $status_div = $('#teaser-error');
  } else {
    $status_div = $('#teaser-status');
  }
  $status_div.html(status);
  setTimeout(function() {
    $status_div.empty('');
  }, 1500);
};

/**
 * Displays beta registration status message and then closes
 * the invitation div by sliding it up and away after 2s.
 */
viewfinder.invite.closeInvite_ = function(speed) {
  $('#teaser-email').off('keypress');
  setTimeout(function() {
    $('#teaser-invite').slideUp(function() {
      $('#teaser-email').val('');
    });
  }, speed || 1500);
};
