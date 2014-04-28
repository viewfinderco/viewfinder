/**
 *
 * @class VFMyInfo
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: The VFMyInfo object which handles any actions stemming from the MyInfo screen
 * @author: Greg Vandenberg
 *
 */
var VFMyInfo = function(_nav) {
  var nav = _nav;
  var util = new VFUtils(_nav);

  return {
    selectAddEmailOrMobile: function() {
      util.pollUntilButtonVisibleTap(BUTTON_ADD_EMAIL_MOBILE, 'add_email', 10);
    },
    selectAdd: function() {
      util.pollUntilButtonVisibleTap(BUTTON_ADD, 'main_window', 5);
    },
    selectContinue: function() {
      var button = util.pollUntilButtonVisible(BUTTON_CONTINUE, 'main_window', 5);
      button.tapAndWaitForInvalid();
    },
    setAccessCode: function(access_code) {
      UIALogger.logDebug("Access Code: " + access_code);
      //target.app().keyboard().typeString(access_code);
      var textField = target.main().images()[1].textFields()[0];
      textField.typeString(access_code,true);
    },
    setEmailAddress: function(email) {
      var textField = target.main().images()[1].textFields()[0];
      textField.typeString(email,true);
    },
    setMobileNumber: function(number) {
      var textField = target.main().images()[1].textFields()[0];
      textField.typeString(number,true);
    }

  }
};

