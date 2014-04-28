// Copyright 2012 Viewfinder Inc. All Rights Reserved.

/**
 * @fileoverview Base javascript include file.
 *
 * @author matt@emailscrubbed.com (Matt Tracy)
 */

viewfinder = {};
viewfinder.flags = {};
viewfinder.messageVersion = 21;


(function(cookies) {
  /**
   * Utility function to retrieve named cookie.
   * Copied from tornado documentation:
   * http://www.tornadoweb.org/documentation/overview.html#xsrf
   *
   * @private
   * @param {String} name of cookie to retrieve.
   *
   * @returns {String} cookie for given name.
   */
  cookies.get = function(name) {
    var r = document.cookie.match("\\b" + name + "=([^;]*)\\b");
    return r ? r[1] : undefined;
  };

  cookies.set = function(name, value, persist) {
    var c = name + '=' + value + ';';
    if (persist) {
      // Expire the cookie in one day.
      var d = new Date();
      d.setTime(d.getTime() + (24*60*60*1000));
      c = c + 'expires=' + d.toGMTString();
    }

    document.cookie = c;
  };

  cookies.clear = function(name) {
    document.cookie = name + '=; expires=Thu, 01 Jan 1970 00:00:01 GMT;';
  };

  cookies.SKIP_PWD_COOKIE = 'skippwd';
})(viewfinder.cookies = {});

(function(fx){
  var isMobile = /mobi/i.test(navigator.userAgent);
  
  fx.animation = !isMobile;
  fx.fixed = !isMobile;
  fx.loading = !isMobile;
  fx.fastclick = isMobile;
})(viewfinder.fx = {});

(function(util) {
  util.shortTimeString = function (datetime) {
    var now = new Date();
    var diff = now.getTime() - datetime.getTime();

    // If this happened on the same calendar day, return just the time.
    if (diff < (24 * 60 * 60 * 1000) && now.getDay() === datetime.getDay()) {
      return datetime.format('h:MMt');
    }

    // If this happened in the last calendar week, use the day name and time.
    if (diff < (7 * 24 * 60 * 60 * 1000) && now.getDay() !== datetime.getDay()) {
      return datetime.format('ddd, h:MMt');
    }

    // If this happened in the same calendar year, display month/date and time.
    if (now.getFullYear() === datetime.getFullYear()) {
      return datetime.format('mmm d, h:MMt');
    }

    // Different year: return the full date.
    return datetime.format('mmm d, yyyy, h:MMt');          
  };

  // Returns a formatted string representing the amount of time since an event happened.
  // If it has been more than a week, a short date is displayed insided.
  util.dateDiffString = function (datetime) {
    var now = new Date();
    var timediff = now.getTime() - datetime.getTime();
    if (timediff < (60 * 60 * 1000)) {
      // Less than an hour different, display minutes.
      return String(Math.floor(timediff / (60 * 1000))) + 'm ago';
    } else if (timediff < (24 * 60 * 60 * 1000)) {
      // Less than a day different, display hours.
      return String(Math.floor(timediff / (60 * 60 * 1000))) + 'h ago';
    } else if (timediff < (7 * 24 * 60 * 60 * 1000)) {
      // Less than a week different, display days.
      return String(Math.floor(timediff / (24 * 60 * 60 * 1000))) + 'd ago';      
    } else if (now.getFullYear() === datetime.getFullYear()) {
      // Same year, simple date is all that is needed.
      return datetime.format('mmm d');
    } else {
      return datetime.format('mmm d, yyyy)');
    }            
  };
})(viewfinder.util = {});

(function(sp){
  extensions = {
    endsWith : function (suffix) {
      return this.indexOf(suffix, this.length - suffix.length) !== -1;
    },
    startsWith : function (prefix) {
      return this.indexOf(prefix) === 0;
    }
  };
  _(sp).defaults(extensions);
})(String.prototype);

(function(mp){
  extensions = {
    randomInt: function (start, end) {
      var diff = end - start;
      return start + Math.floor(Math.random() * (diff + 1));
    }
  };
  _(mp).defaults(extensions);
})(Math);

(function(_) {
  _.mixin({
    // Optimized debounce for the case when the timer is 0.
    simpleDebounce : function (func) {
      var timeout = null;
      return function() {
        if (timeout) return;
        var context = this, args = arguments;
        var later = function() {
          timeout = null;
          func.apply(context, args);
        };
        timeout = setTimeout(later, 0);
      };
    },
    
    // Debounce that calls a different method if it is called
    // multiple times before its actual invocation.
    multiplexDebounce : function (singleFunc, multiFunc) {
      var timeout = null;
      var callCount = 0; 
      return function () {
        callCount++;
        if (timeout) return;
        var context = this, args = arguments;
        var later = function () {
          timeout = null;
          var finalCallCount = callCount;
          callCount = 0;
          if (finalCallCount === 1) {
            singleFunc.apply(context, args);
          } else {
            multiFunc.apply(context, args);
          }
        };   
        
        timeout = setTimeout(later, 0);
      };
    },
    
    // Simple sum.
    sum : function (list, iter) {
      var total = 0;
      _(list).each(function (x) {
        total += iter(x);
      });
      return total;
    }
  });
})(_);
