/**
 * The Login object which handles any actions stemming from the Login screen
 * @class VFAddContacts
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: The Login object which handles any actions stemming from the Login screen
 * @author: Greg Vandenberg
 *
 */
var VFLogin = function(_nav) {
  var nav = _nav;
  var count = 0;
  var util = new VFUtils(_nav);

  return {
    getCount: function() {
      return (type(target.main().images()[1].textFields()[0]) == 'UIATextField') ? 1 : 2;
    },
    setValidEmailFormat: function(email) {
      count = this.getCount();
      var textField = target.main().images()[count].textFields()[0];
      textField.typeString(email, true);

    },
    setInvalidEmailFormat: function() {
      count = this.getCount();
      var textField = target.main().images()[count].textFields()[0];
      var invalid_format = 'tester';
      textField.typeString(invalid_format, true);
    },
    setPassword: function(password) {
      count = this.getCount();
      var textField = target.main().images()[count+1].secureTextFields()[0];
      textField.typeString(password, true);
    },
    setNewPassword: function(password) {
      target.pushTimeout(5);
      var textField = target.main().images()[1].secureTextFields().firstWithPredicate("value like 'New Password'");
      target.popTimeout();
      if (util.type(textField) != 'UIAElementNil') {
        textField.typeString(password, true);
      }
      else {
        throw new Exception("Could not find 'New Password' textfield.");
      }

    },
    setConfirmPassword: function(password) {
      var textField = target.main().images()[2].secureTextFields()[0];
      if (util.type(textField) != 'UIAElementNil') {
        textField.typeString(password, true);
      }
      else {
        throw new Exception("Could not find 'Confirm Password' textfield.");
      }
    },
    selectLogin: function() {
      /**
       * without having unique identifier for the login form button,
       * do this workaround
       */
      var rect_y = (target.isDeviceiPad()) ? 300 : 100; // TODO: calculate from window size
      var buttons = target.main().buttons();
      var login_button = null;
      for (var i=0; i<buttons.length; i++) {
        var rect = buttons[i].rect();
        var name = buttons[i].name();
        if (name == 'Log In' && rect.origin.y > rect_y) {
          login_button = buttons[i];
          break;
        }
      }
      var rect = login_button.rect();
      if (login_button != null) {
        login_button.vtap();
        login_button.waitForInvalid();
      }
      else {
        throw new Exception("Could not find 'Log In' button.");
      }
    },
    selectCancel: function() {
      var button = util.pollUntilButtonVisible(BUTTON_CANCEL, 'main_window', 5);
      nav.tapButton(button);
    },
    selectForgotPassword: function() {
      var button = util.pollUntilButtonVisible(BUTTON_FORGOT_PASSWORD, 'main_window', 5);
      nav.tapButton(button);
    },
    selectBack: function() {
      var button = util.pollUntilButtonVisible(BUTTON_BACK, 'main_window', 5);
      nav.tapButton(button);
    },
    selectSubmit: function() {
      var button = util.pollUntilButtonVisible(BUTTON_SUBMIT, 'main_window', 5);
      nav.tapButton(button);
    }
  }
};
