/**
 *
 * @class VFOnboarding
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: The onboarding object which handles any actions stemming from the Onboarding screen
 * @author: Greg Vandenberg
 *
 */

var VFOnboarding = function(_nav) {
  _self = this;
  nav = _nav;
  _signup = null;
  _login = null;
  var util = new VFUtils(_nav);

  function introPageNavigation(indicator) {
    for (var i=0; i<5; i++) {
      nav.swipeRightToLeft();
      target.delay(1); // TODO: change to polling for visible
      var page = target.main().pageIndicators()[0];
      if (page.checkIsValid() && page.value() == indicator) {
        return true;
      }
    }
    return false;
  }

  return {
    login: function() {
      if (_self._login == null) {
        _self._login = new VFLogin(nav);
      }
      return _self._login;
    },
    signup: function() {
      if (_self._signup == null) {
        _self._signup = new VFSignup(nav);
      }
      return _self._signup;
    },
    loginUser: function(user) {
      try{
        this.gotoLogin();
        this.login().setValidEmailFormat(user.email);
        this.login().setPassword(user.password);
        this.login().selectLogin();
        return true;
      }
      catch(err) {
        return false;
      }
    },
    gotoLogin: function() {
      target.delay(2);
      var button = util.pollUntilButtonVisible(BUTTON_LOGIN, 'main_window', 5);
      button.vtap();
      return true;
    },
    gotoSignup: function() {
      target.delay(2);
      var button = util.pollUntilButtonVisible(BUTTON_SIGNUP, 'main_window', 5);
      button.vtap();
      return true;
    },
    gotoIntroDashboard: function() {
      return introPageNavigation('page 2 of 4');
    },
    gotoIntroLibrary: function() {
      return introPageNavigation('page 3 of 4');
    },
    gotoIntroConversation: function() {
      return introPageNavigation('page 4 of 4');
    }
  }
};



