/**
 * The utility class for global operations
 * @class VFUtils
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: Utility functions for global operations
 * @author: Greg Vandenberg
 *
 */
var VFUtils = function (_nav, _testname) {
  var vf = new Viewfinder(false);
  var nav = _nav;
  var testname = _testname;
  return {
    selectBackNav: function() {
      // TODO: this button is elusive, find better way to get at it
      target.app().tapWithOptions({tapOffset:{x:0.10, y:0.05}});
      /**
       * below is how to access the button according to logElementTree(),
       * however it does not work
       */
      //target.frontMostApp().navigationBar().buttons()["toolbar back nav"].tap();
    },
    invokeQueryNotifications: function() {
      target.deactivateAppForDuration(1);
    },
    isPlaceholderGraphic: function (image) {
      var rect = image.rect();
      return (rect.size.height == 177 && rect.size.width == 308 ) ? true : false;
    },
    getImages: function(images) {
      valid = [];
      var win = target.main().rect();
      for (var i=0; i<images.length; i++) {
        if (images[i].isValid() && images[i].name() == null && !this.isPlaceholderGraphic(images[i])) {
          //find an image on the screen
          var h = images[i].rect().size.height;
          var w = images[i].rect().size.width;
          var x = images[i].rect().origin.x;
          var y = images[i].rect().origin.y;

          if (x < 260 && y < (win.size.height - 20) && h > 60 && w < 320 && w > 60) {
            name = images[i].name();
            if (!name) {
              if (!(w > 300 && h < 80)) {
                valid.push(images[i]);
              }
            }
          }
        }
      }
      return valid;
    },
    selectImage: function(image, scrollView) {
      var win = target.main().rect();
      rect = image.rect();
      width = rect.size.width;
      height = rect.size.height;
      x_origin = rect.origin.x;
      y_origin = rect.origin.y;  // TODO: look into offset 54
      if (DEBUG) {
        UIALogger.logDebug("y width: " + width);
        UIALogger.logDebug("x height: " + height);
        UIALogger.logDebug("x origin: " + x_origin);
        UIALogger.logDebug("y origin: " + y_origin);
      }
      x = x_origin + (width / 2);
      y = y_origin + (height / 2);
      if (DEBUG) {
        UIALogger.logDebug("x: " + x);
        UIALogger.logDebug("y: " + y);
      }
      x_offset = (x / win.size.width).toFixed(2);
      y_offset = (y / (win.size.height - 20)).toFixed(2);
      if (DEBUG) {
        UIALogger.logDebug("x_offset: " + x_offset);
        UIALogger.logDebug("y_offset: " + y_offset);
      }
      var sv = scrollView;
      sv.tapWithOptions({tapOffset:{x:x_offset, y:y_offset}});
    },
    dismissAlert: function(button_name) {
      try{
        var hitpoint = target.frontMostApp().alert().buttons()[0].hitpoint();
        target.frontMostApp().tapHitPoint(hitpoint);
      }
      catch(err) {
        target.delay(1);
        var hitpoint = target.frontMostApp().alert().buttons()[0].hitpoint();
        target.frontMostApp().tapHitPoint(hitpoint);
      }
    },
    delay: function(seconds) {
      target.delay(seconds);
    },
    safeTap: function(obj) {
      if (this.type(obj) != 'UIAElementNil' && obj.isVisible()) {
        obj.tap();
        return true;
      }
      return false;
    },
    clone: function(obj) {
      if(obj == null || typeof(obj) != 'object'){
        return obj;
      }

      var temp = new obj.constructor();
      for(var key in obj){
        temp[key] = this.clone(obj[key]);
      }
      return temp;
    },
    requestTemplate: {
      'headers': {
        'version': 16
      }
    },
    getNav: function() {
      return nav;
    },
    getLoggedInUserId: function() {
      return LOGGED_IN_USERID;
    },
    setLoggedInUserId: function(id) {
      LOGGED_IN_USERID = id;
    },
    gotoDashboard: function() {
      var status = 0;
      /**
       * check if we are already on dashboard by verifying that the
       * 'Settings' button is visible
       */
      if (this.isTopLevelScreen(main.DASHBOARD) == true) {
        UIALogger.logDebug("On Dashboard.");
        target.delay(1);
        return new VFDashboard();
      }
      else {
        UIALogger.logDebug("Not on dashboard yet.");
      }

      /**
       * check for presence of a "back" button
       * tap button if present
       */
      nav.tapButton(nav.getButton(BUTTON_BACK, 'main_window'));

      /**
       * check for dialog dismiss button
       */
      nav.tapButton(nav.getButton(BUTTON_DISMISS_DIALOG, 'navbar'));

      /**
       * check for presence of an "exit" button
       * tap button if present
       */
      nav.tapButton(nav.getButton(BUTTON_EXIT, 'main_window'));

      /**
       * At this point we should be at the top level,
       * the swipe action is flaky, try up to 5 swipes to get to
       * the dashboard
       */
      for (var i=0; i<5; i++) {
        nav.swipeLeftToRight();
        target.delay(1);  // TODO: change to a poll for visible
        if (this.isTopLevelScreen(main.DASHBOARD) == true) {
          UIALogger.logDebug("On Dashboard after swipes.");
          status = 1
          break;
        }
        else {
          UIALogger.logDebug("Can't find Dashboard identifying button");
        }
      }

      if (status) {
        return new VFDashboard();
      }
      else {
        throw "gotoDashBoard() unsuccessful.";
      }
    },
    /**
     * Get the specified button object if visible
     *
     * @method getButton
     * @param {string} name the name of the button to be retrieved
     * @return UIAButton
     */
    isButtonVisible: function(button) {
      return (this.type(button) == 'UIAButton' && button.isVisible()) ? 1 : 0;
    },
    /**
     * Given a button that is on the dashboard, keep
     * track of x origins for all top level screens
     */
    getDashboardButtonOrigin: function(btn) {
      var win = target.main().rect();
      if (target.isDeviceiPad()) {
        win = target.frontMostApp().windows()[0].rect();
      }
      var origin = btn.rect().origin;
      var num_screens = 3;
      var x = origin.x;
      var width = win.size.width;
      UIALogger.logDebug("Win width: " + width);
      var origins = [];
      var lower_bound = -Math.abs(width * (num_screens - 1));

      if ((x - width) < lower_bound) {
        origins[0] = x;
      }
      else {
        while((x - width) > lower_bound) {
          origins[0] = x - width;
          x = x - width;
        }
      }
      for (var i=0; i<num_screens; i++) {
        if ((origins[i] + width) <= width) {
          origins[i+1] = origins[i] + width;
        }
      }
      for (var j=0; j<origins.length; j++) {
        if (origins[j] > width) {
          origins[j] = -Math.abs(origins[j]);
        }
      }
      return origins.reverse();
    },
    /**
     * Utility method to check if you are at the
     * specified top-level screen
     */
    isTopLevelScreen: function(screen) {
      var loc = screen;
      var btn = this.pollUntilButtonValid(BUTTON_DASHBOARD_ID, 'main', 5);
      var rect = null;
      try {
        rect = btn.rect();
      }
      catch(err) {
        target.delay(2);
        btn = this.pollUntilButtonValid(BUTTON_DASHBOARD_ID, 'main', 5);
        if (type(btn) == 'UIAButton')
          rect = btn.rect();
      }
      var origins = this.getDashboardButtonOrigin(btn);
      UIALogger.logDebug("origins.x: " + rect.origin.x);
      UIALogger.logDebug("origins[loc]: " + origins[loc]);
      if (rect.origin.x == origins[loc]) {
        return true;
      }
      return false;
    },
    /**
     * We need to trim the status bar from the screen shots because it
     * includes the time. Including the status bar would result in screen shots
     * being continuously different from the baseline
     * @method screenCapture
     * @param {string} name of the image (will be stored on disk as 'name.png')
     */
    screenCapture: function(name) {
      for (var i=0; i<2; i++) {
        target.captureAppScreenWithName(name+"|"+i);
        target.delay(.5); // Need a moment for writing image to disk
        if (this.isImageEqual(testname, name + "|" + i + ".png")) {
          return;
        }
        else {
          // allow UI to settle before the screen shot
          UIALogger.logDebug("Wating for UI to settle for screenshot.")
          target.delay(.5);
        }
      }
    },
    setupCleanStateAll: function(runState) {
      switch(runState) {
      case 0: // ONBOARDING
        /**
         * For now, this case does nothing since the user login and
         * termination was moved to the Python control script.
         */
        break;
      case 1: // DASHBOARD
        /**
         * This mode will start your test logged in and navigate
         * to the dashboard.
         */
        var ob = new VFOnboarding(nav);
        var user = new VFUser();
        var t = TEST_USERS[0];
        try {
          user.register(t);
          ob.loginUser(t);
          UIALogger.logDebug("User should be logged in.");
        }
        catch(err) {
          throw new Exception("An error occured contacting viewfinder server.");
        }
        /**
         * by default, after login we go to the Dashboard.
         * We need to dismiss tutorial.
         */
        this.selectDismissSwipeTutorial();
        break;
      default:
      }
    },
    /**
     * determine the specified object's type
     *
     * @method type
     * @param {object} obj
     * @return {string}
     */
    type: function(obj) {
      return Object.prototype.toString.call(obj).match(/^\[object (.*)\]$/)[1];
    },
    timeout: function(timeout) {
      return typeof timeout !== 'undefined' ? timeout : 5;
    },
    pollUntilElementVisibleTap: function(_element, _timeout) {
      timeout = this.timeout(_timeout);
      var element = this.pollUntilElementVisible(_element, timeout);
      try {
        element.waitUntilVisible(5);
        element.tap();
      }
      catch(err) {
        throw new Exception ("An error occured pollUntilElementVisibleTap()");
      }
    },
    pollUntilElementVisible: function(_element, _timeout) {
      timeout = this.timeout(_timeout);
      for (var i=0; i<(timeout*4); i++) {
        var element = _element;
        if (this.type(element) == 'UIAElementNil') {
          target.delay(.25);
        }
        else {
          return element;
        }
      }
      throw new Exception("Never found specified element: " + _element);
    },
    pollUntilButtonVisible: function(button_name, sect, _timeout) {
      timeout = this.timeout(_timeout);
      var button = null;
      for (var i=0; i<(timeout*4); i++) {
        button = nav.getButton(button_name, sect, 0);
        UIALogger.logDebug("Polling for button: " + button_name);
        if (this.type(button) == 'UIAButton') {
          if (button.isVisible()) {
            UIALogger.logDebug("Found button: " + button_name);
            return button;
          }
        }
        target.delay(.25);
      }
      throw new Exception("Never found specified button: " + button_name);
    },
    pollUntilButtonVisibleTap: function(button_name, sect, _timeout) {
      timeout = this.timeout(_timeout);
      var button = this.pollUntilButtonVisible(button_name, sect, timeout);
      button.vtap();
    },
    pollUntilButtonValid: function(button_name, sect, _timeout) {
      timeout = this.timeout(_timeout);
      var button = null;
      for (var i=0; i<(timeout*4); i++) {
        button = nav.getButton(button_name, sect, 0);
        UIALogger.logDebug("Attempting to retrieve button: " + button_name + ", " + sect);
        if (this.type(button) == 'UIAButton') {
          if (button.isValid()) {
            UIALogger.logDebug("Found button: " + button_name);
            return button;
          }
        }
        target.delay(.25);
      }
      throw new Exception("Never found specified button: " + button_name);
    },
    // select swipe tutorial to dismiss
    selectDismissSwipeTutorial: function() {
      try {
        this.pollUntilButtonVisibleTap(BUTTON_SWIPE_TUTORIAL, 'main_window', 5);
      }
      catch(err) {
        // eat exception
      }
    },
    isImageEqual: function(test_name, image_name) {
      var request = this.clone(this.requestTemplate);
      var response = false;
      request.testname = test_name;
      request.imagename = image_name;
      request.scheme = scheme;
      try {
        var result = vf.is_image_equal(request, null);
        //success
        UIALogger.logDebug("Successfully evaluated images " + result.stdout);
        response = (JSON.parse(result.stdout)).response;
      }
      catch(err) {
        UIALogger.logDebug("Images do not match.");
      }

      return response;
    }
  }


};
