/**
 * The navigation object which handles any actions (button tap, swipes, etc...)
 * @class VFNavigation
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: The navigation object which handles any actions (button tap, swipes, etc...)
 * @author: Greg Vandenberg
 *
 */

var VFNavigation = function() {
  var buttons = null;
  /**
   * grab the current set of discoverable buttons
   *
   * @method setupButtons
   * @param app
   * @param main
   * @returns {Array}
   */
  function setupButtons(sect) {
    var target = UIATarget.localTarget();
    UIALogger.logDebug('refresh: ' + sect);
    var buttonList = [];
    var buttonLists = [];
    switch(sect) {
    case 'add_email':
      var tableView = target.main().tableViews()["Empty list"];
      var buttons = tableView.cells()["Add Email or Mobile"].buttons();
      buttonLists = [buttons];
      break;
    case 'segmented':
      var buttons = target.main().segmentedControls()[0].buttons();
      buttonLists = [buttons];
      break;
    case 'toolbar':
      var buttons = target.main().toolbar().buttons();
      var buttons1 = target.app().windows()[1].toolbar().buttons();
      buttonLists = [buttons, buttons1];
      break;
    /*
     * These are the button states that are refreshed via nav.refresh('navbar');
     *
     * target.app().navigationBar().buttons()["dismiss dialog"];
     * target.app().navigationBar().buttons()["toolbar back nav"]; TODO:  figure out how to get at this button
     *
     */
    case 'navbar':
      var navButtons = target.main().navigationBar().buttons();
      buttonLists = [navButtons];
      break;
    /*
     * These are the button states that are refreshed via nav.refresh('unlink');
     *
     * target.app().tableViews()["Empty list"].cells()["Unlink iPhone from Viewfinder"].buttons()
     *
     */
    case 'unlink':
      var tblviews = target.main().tableViews()[0];
      var buttons = tblviews.cells()["Unlink iPhone from Viewfinder"].buttons();
      buttonLists = [buttons];
      break;
    /*
     * These are the button states that are refreshed via nav.refresh('main_window');
     *
     * target.main().buttons()["Back"];
     * target.main().buttons()["Exit"];
     * target.main().buttons()["Sign Up"];
     * target.main().buttons()["Cancel"];
     * target.main().buttons()["Log In"];
     * target.main().buttons()["Create Account"];
     * target.main().buttons()["Continue"];
     *
     */
    case 'main_window':
      var buttons = target.main().buttons();
      buttonLists = [buttons];
      break;
    /*
     * These are the button states that are refreshed via nav.refresh('main');
     *
     * target.main().scrollViews()[0].scrollViews()[0].buttons()["Add Your Contacts"];
     * target.main().scrollViews()[0].scrollViews()[0].buttons()["Contacts"];
     * target.main().scrollViews()[0].scrollViews()[0].buttons()["Conversation Feed"];
     * target.main().scrollViews()[0].scrollViews()[0].buttons()["My Info"];
     * target.main().scrollViews()[0].scrollViews()[0].buttons()["Personal Library"];
     * target.main().scrollViews()[0].scrollViews()[0].buttons()["Settings"];
     *
     * target.main().scrollViews()[0].buttons()["Exit"];
     * target.main().scrollViews()[0].buttons()["Search"];
     * target.main().scrollViews()[0].buttons()["Camera"];
     * target.main().scrollViews()[0].buttons()["Compose"];
     * target.main().scrollViews()[0].buttons()["Action"];
     * target.main().scrollViews()[0].buttons()["Export"];
     * target.main().scrollViews()[0].buttons()["Share"];
     *
     */
    case 'main':
      var buttons = target.main().scrollViews()[0].scrollViews()[0].buttons();
      var mainButtons = target.main().scrollViews()[0].buttons();
      buttonLists = [buttons, mainButtons];
      break;
    case 'contacts':
      var buttons1 = target.main().scrollViews()[0].images()[1].buttons();
      var buttons2 = target.main().scrollViews()[0].images()[2].buttons();
      var buttons3 = target.main().scrollViews()[0].images()[3].buttons();
      var buttons4 = target.main().scrollViews()[0].images()[4].buttons();
      var buttons5 = target.main().scrollViews()[0].images()[5].buttons();
      var buttons6 = target.main().scrollViews()[0].images()[6].buttons();
      buttonLists = [buttons1, buttons2, buttons3, buttons4, buttons5, buttons6];
      break;
    case 'action':
      var buttons = target.app().actionSheet().buttons();
      buttonLists = [buttons];
      break;
    case 'webview':
      var buttons = target.main().scrollViews()[1].webViews()[0].buttons();
      buttonLists = [buttons];
      break;
    case 'library':
      var buttons = target.main().scrollViews()[0].scrollViews()[1].buttons();
      buttonLists = [buttons];
      break;
    default:
      var navButtons = target.app().navigationBar().buttons();
      var tblviews = target.main().tableViews()[0];
      var unlink_buttons = tblviews.cells()["Unlink iPhone from Viewfinder"].buttons();
      var main_buttons = target.main().buttons();
      var buttons1 = target.main().scrollViews()[0].scrollViews()[0].buttons();
      var mainButtons = target.main().scrollViews()[0].buttons();
      var buttons2 = target.app().actionSheet().buttons();
      buttonLists = [navButtons, unlink_buttons, main_buttons, buttons1, mainButtons, buttons2];
    }
    /**
     * this loop is to add all elements to buttonList array.
     * array.concat(array) does not work properly
     */
    for (var x=0; x<buttonLists.length; x++) {
      tmpButtonList = buttonLists[x];
      for(var y=0; y<tmpButtonList.length; y++) {
        buttonList.push(tmpButtonList[y]);
      }
    }
    return buttonList;

  }

  return {
    /**
     * refresh the current state of the buttons
     *
     * @method refresh
     * @param {string} sect
     *
     */
    refresh: function(sect) {
      buttons = setupButtons(sect);
    },
    /**
     * Get the specified button object if visible
     *
     * @method getButton
     * @param {string} name the name of the button to be retrieved
     * @return UIAButton
     */
    getButton: function(name, refresh, visible) {
      this.refresh(refresh);
      if (buttons) {
        for (var j=0; j<buttons.length; j++) {
          var button = buttons[j];
          if (type(button) == 'UIAButton' && button.name()) {

            var btn_name = button.name();
            var isVisible = button.isVisible();
            /*
             * this assumes that two buttons with the same
             * name are not visible at the same time
             */
            if (btn_name == name && isVisible) {
              return button;
            }
            else if (btn_name == name && visible == 0) {
              return button;
            }
          }
        }
        UIALogger.logDebug("Error occured accessing button: " + name);
        return null;
      }
    },
    /**
     * Scroll down to ensure current page is at top
     *
     * @method scrollToPageTop
     *
     */
    scrollToPageTop: function() {
      target.app().target.flickFromTo({x:160, y:60}, {x:160, y:180});
      target.localTarget().delay(STANDARD_TIMEOUT_IN_SECONDS);
    },
    /**
     * UI Swipe from left to right.  The delays are necessary
     * because the simulator UI is finicky.
     *
     * @method swipeLeftToRight
     *
     */
    swipeLeftToRight: function() {
      target.flickInsideWithOptions({startOffset:{x:0.2, y:0.5}, endOffset:{x:0.8, y:0.5}});
    },
    /**
     * UI Swipe from right to left.  The delays are necessary
     * because the UI is finicky.
     *
     * @method swipeRightToLeft
     *
     */
    swipeRightToLeft: function() {
      target.flickInsideWithOptions({startOffset:{x:0.8, y:0.5}, endOffset:{x:0.2, y:0.5}});
    },
    /**
     * Tap the specified button.  Assumes that the specified button is
     * a UIAButton object and is visible in the UI
     *
     * @method tapButton
     * @param {UIAButton} button button to be tapped
     * @returns {int} 1 for success, 0 for failure
     *
     */
    tapButton: function(button) {
      if (type(button) == 'UIAButton') {
        var name = button.name();
        UIALogger.logDebug("button visible: " + button.isVisible());
        try {
          UIALogger.logDebug("attempt button tap: " + button.name());
          button.tap();
          button.waitForInvalid();
        }
        catch (err) {
          UIALogger.logDebug("Error occured tapping button: " + button.name());
        }
        if (button.isVisible() && name == button.name()) {
          UIALogger.logDebug("button still visible: " + button.name());
          try {
            UIALogger.logDebug("Retry button tap: " + button.name());
            button.tap();
          }
          catch (err) {
            UIALogger.logDebug("Error occured tapping button: " + button.name());
          }
        }
        return true;
      }
      else {
        /**
         * If we get to this point and the button is not a UIAButton, do a refresh of all
         * the buttons via the underlying accessibility framework and
         * retry a tap.
         */
        button = this.getButton(name, null);
        if (button) {
          button.tap();
          return true;
        }

      }
      UIALogger.logDebug('button not tapped: ' + type(button));
      return false;
    }
  }
}
