// Copyright 2012 Viewfinder Inc. All Rights Reserved.

/**
 * @fileoverview identity linking routines for handling mobile
 *   devices intelligently if the app is installed.
 *
 * @author spencer@emailscrubbed.com (Spencer Kimball)
 */

viewfinder.idlink = {};

/**
 * Redirects to the application using iOS's provision for custom
 * URL schemes. We use 'viewfinder://idlink'. We catch any errors
 * and redirect to the web application instead.
 *
 * TODO(spencer): currently it redirects to the web interface as we're
 *   not yet on the app store. In the future, we're going to simply
 *   want to display a message saying the app does not appear to be
 *   installed and allow them to choose between the web application
 *   or the app store.
 */
viewfinder.idlink.redirectToApp = function(appUrl, noAppUrl) {
  try {
    window.location=appUrl;
  } catch(e) {
    window.location=noAppUrl;
  }
};
