/**
 *
 * @class VFDashboard
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: The dashboard object which handles any actions stemming from the dashboard.
 * @author: Greg Vandenberg
 *
 */

var VFDashboard = function() {
  var nav = new VFNavigation();
  var util = new VFUtils(nav);

  return {
    /**
     * Select the Personal Library from the Dashboard
     *
     * @method gotoLibrary
     * @returns VFPersonalLibrary
     *
     */
    gotoLibrary: function() {
      return this.gotoTopLevelScreen(main.LIBRARY);
    },
    /**
     * Select the Conversation Feed from the Dashboard
     *
     * @method gotoConversations
     * @returns VFConversation
     *
     */
    gotoConversations: function() {
      return this.gotoTopLevelScreen(main.INBOX);
    },
    /**
     * Convenience method to navigate top-level screens
     *
     * @method gotoTopLevelScreen
     * @returns Object
     */
    gotoTopLevelScreen: function(screen) {
      /**
       * We are at the dashboard,
       * the swipe action is flaky, try up to 5 swipes to get to
       * a specified top level screen
       */
      for (var i=0; i<5; i++) {
        nav.swipeRightToLeft();
        target.delay(1);
        if (util.isTopLevelScreen(screen) == true) {
          switch(screen) {
            case 1:
              UIALogger.logDebug("At Library after swipes.");
              return new VFPersonalLibrary(nav);
            case 2:
              UIALogger.logDebug("At Inbox after swipes.");
              return new VFConversation(nav);
            default:
              throw new Exception('Can\'t find screen');
          }
        }
      }
      throw new Exception('Can\'t find requested top level screen');
    },
    /**
     * Select the Contacts from the Dashboard
     *
     * @method gotoContacts
     * @returns VFContacts
     *
     */
    gotoContacts: function() {
      var button = util.pollUntilButtonVisible(BUTTON_CONTACTS, 'main', 5);
      nav.tapButton(button);
      UIALogger.logDebug("On Contact Screen.");
      return new VFContacts(nav);
    },
    /**
     * Select the Settings from the Dashboard
     *
     * @method gotoSettings
     * @returns VFSettings
     *
     */
    gotoSettings: function() {
      var button = util.pollUntilButtonVisible(BUTTON_SETTINGS, 'main', 5);
      nav.tapButton(button);
      UIALogger.logDebug("On Settings Screen.");
      return new VFSettings(nav);
    },
    /**
     * Select the 'My Info' button from the Dashboard
     *
     * @method gotoSettings
     * @returns VFSettings
     *
     */
    gotoMyInfo: function() {
      var button = util.pollUntilButtonVisibleTap(BUTTON_MYINFO, 'main', 5);
      /**
       * there is an intermittent issue that pops up here... on occasion after you select
       * the 'My Info' button it hangs at a screen with 'Contact Info' at the top
       * logged as Issue #433
       */

      UIALogger.logDebug("On My Info Screen.");
      return new VFMyInfo(nav);
    }
  }
};

