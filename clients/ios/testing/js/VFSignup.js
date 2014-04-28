/**
 *
 * @class VFSignup
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: The Signup object which handles any actions stemming from the Signup screen
 * @author: Greg Vandenberg
 *
 */
var VFSignup = function(_nav) {
  var nav = _nav;
  var count = 0;
  var util = new VFUtils(_nav);

  return {
    /**
     * This function getCount() will remain as a workaround until we can get all
     * the labels we need for testing integrated into the client.
     */
    getCount: function() {
      return (type(target.main().images()[1].textFields()[0]) == 'UIATextField') ? 1 : 2;
    },
    setFirstName: function(name) {
      count = this.getCount();
      var textField = target.main().images()[count].textFields()[0];
      textField.typeString(name, true);
    },
    setLastName: function(name) {
      count = this.getCount();
      var textField = target.main().images()[count].textFields()[1];
      textField.typeString(name, true);
    },
    setValidEmailFormat: function(email) {
      count = this.getCount();
      var textField = target.main().images()[count + 1].textFields()[0];
      textField.typeString(email, true);
    },
    setInvalidEmailFormat: function() {
      count = this.getCount();
      var textField = target.main().images()[count + 1].textFields()[0];
      var invalid_format = 'tester';
      textField.typeString(invalid_format, true);
    },
    setPassword: function(password) {
      count = this.getCount();
      var textField = target.main().images()[count + 2].secureTextFields()[0];
      textField.typeString(password, true);
    },
    setAccessCode: function(code) {
      count = this.getCount();
      var textField = target.main().images()[count].textFields()[0];
      textField.typeString(code, true);
    },
    selectCreateAccount: function() {
      util.pollUntilButtonVisibleTap(BUTTON_CREATE_ACCOUNT, 'main_window', 5);
    },
    selectCancel: function() {
      // this line did not work with 2.1.0.70.dev
      // it seems to be working again
      var button = util.pollUntilButtonVisible(BUTTON_CANCEL, 'main_window', 5);
      //var button = target.main().buttons()[3];
      return nav.tapButton(button);
    },
    selectExit: function() {
      var button = util.pollUntilButtonVisible(BUTTON_EXIT, 'main_window', 5);
      return nav.tapButton(button);
    },
    selectSendCodeAgain: function() {
      util.pollUntilButtonVisibleTap(BUTTON_SEND_CODE_AGAIN, 'main_window', 5);
    },
    selectContinue: function() {
      util.pollUntilButtonVisibleTap(BUTTON_CONTINUE, 'main_window', 5);
    }
  }
};
