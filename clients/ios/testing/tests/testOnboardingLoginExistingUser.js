/**
 *
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: From an unlinked state, login with new user (terminated) and
 * an existing user
 * @author: Greg Vandenberg
 *
 */

VFRunTest("testOnboardingLoginExistingUser", runStateEnum.ONBOARDING, function(testname, util, log) {

  var ob = new VFOnboarding(util.getNav());
  var t = TEST_USERS[0];
  var user = new VFUser();
  user.register(t);

  log.debug("------------------------------------");
  log.debug("Start Login process (invalid email).");
  log.debug("------------------------------------");
  ob.gotoLogin();
  util.screenCapture('login_form');
  ob.login().setInvalidEmailFormat();
  ob.login().setPassword(t.password);
  target.delay(2); // for accurate screen shot
  util.screenCapture('login_form_filled_out');
  ob.login().selectLogin();

  util.screenCapture('login_invalid_email_error');
  util.dismissAlert("Let me fix that...");

  log.debug("------------------------------------");
  log.debug("Login with invalid account.");
  log.debug("------------------------------------");
  ob.login().setValidEmailFormat('invalid@email.com');
  ob.login().setPassword(t.password);
  ob.login().selectLogin();
  util.screenCapture('login_invalid_user_error');
  util.dismissAlert("OK");
  ob.login().selectCancel();

  log.debug("------------------------------------");
  log.debug("Login with 3 character password.");
  log.debug("------------------------------------");
  ob.gotoLogin();
  ob.login().setValidEmailFormat(t.email);
  ob.login().setPassword('foo');
  ob.login().selectLogin();
  util.screenCapture('login_incorrect_password_error');
  util.dismissAlert("OK");
  ob.login().selectCancel();

  log.debug("------------------------------------");
  log.debug("Forgot password: clear email and password text if necessary");
  log.debug("------------------------------------");
  ob.gotoLogin();
  ob.login().setPassword('');
  ob.login().setValidEmailFormat('');
  ob.login().selectForgotPassword();

  log.debug("------------------------------------");
  log.debug("Forgot password:  Select 'Back'. Set valid email");
  log.debug("------------------------------------");
  ob.login().selectBack();
  ob.login().setValidEmailFormat(t.email);
  ob.login().selectForgotPassword();
  ob.login().selectSubmit();

  log.debug("------------------------------------");
  log.debug("Forgot password:  Get Access Code... Continue.");
  log.debug("------------------------------------");
  util.screenCapture('login_set_access_code');
  var access_code = user.get_access_code('Email:'+t.email);
  ob.signup().setAccessCode(access_code);
  ob.signup().selectContinue();

  log.debug("------------------------------------");
  log.debug("Forgot password:  Set new password (currently broken by issue #493)");
  log.debug("------------------------------------");
  ob.login().setNewPassword(t.password);
  ob.login().setConfirmPassword(t.password);
  util.screenCapture('login_confirm_password');
  ob.login().selectSubmit();

  target.delay(2); // for accurate screen shot
  util.screenCapture('logged_in_dashboard2');



});
