// Copyright 2012 Viewfinder Inc. All Rights Reserved.

/**
 * @fileoverview cookie utility methods to set, get & delete.
 *
 * http://www.quirksmode.org/js/cookies.html
 *
 * @author spencer@emailscrubbed.com (Spencer Kimball)
 */

viewfinder.cookie = {};

viewfinder.cookie.setCookie = function(name, value, days) {
  if (days) {
    var date = new Date();
    date.setTime(date.getTime()+(days*24*60*60*1000));
    var expires = "; expires="+date.toGMTString();
  }
  else var expires = "";
  document.cookie = name+"="+value+expires+"; path=/";
};

viewfinder.cookie.getCookie = function(name) {
  var nameEQ = name + "=";
  var ca = document.cookie.split(';');
  for(var i=0;i < ca.length;i++) {
    var c = ca[i];
    while (c.charAt(0)==' ') c = c.substring(1,c.length);
    if (c.indexOf(nameEQ) == 0) return c.substring(nameEQ.length,c.length);
  }
  return null;
};

viewfinder.cookie.deleteCookie = function(name) {
  viewfinder.cookie.setCookie(name,"",-1);
};
