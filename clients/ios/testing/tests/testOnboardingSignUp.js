/**
 *
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: From an unlinked state, sign up with new user (terminated) and
 * an existing user
 * @author: Greg Vandenberg
 *
 */

VFRunTest("testOnboardingSignUp", runStateEnum.ONBOARDING, function(testname, util, log) {

  var ob = new VFOnboarding(util.getNav());
  // TODO(ben): the flick gesture doesn't seem to be working.
  /*log.debug("------------------------------------");
  log.debug("Explore intro screens.");
  log.debug("------------------------------------");
  assertTrue(ob.gotoIntroDashboard(),"At intro dashboard.");
  util.screenCapture("At_intro_dashboard");
  assertTrue(ob.gotoIntroLibrary(),"At intro library.");
  util.screenCapture("At_intro_library");
  assertTrue(ob.gotoIntroConversation(),"At intro inbox.");
  util.screenCapture("At_intro_inbox");*/

  log.debug("------------------------------------");
  log.debug("Start Sign Up process (invalid user).");
  log.debug("------------------------------------");

  var nav = util.getNav();
  var user = new VFUser();

  assertTrue(ob.gotoSignup(),"At signup form.");

  var t = TEST_USERS[0];
  ob.signup().setFirstName(t.firstname);
  ob.signup().setLastName(t.lastname);
  ob.signup().setInvalidEmailFormat();
  ob.signup().setPassword(t.password);
  ob.signup().selectCreateAccount();
  util.screenCapture('signup_form_filled_out_incorrect');

  util.dismissAlert("Let me fix that...");

  log.debug("------------------------------------");
  log.debug("Sign up: 3 character password.");
  log.debug("------------------------------------");
  ob.signup().setValidEmailFormat(t.email);
  ob.signup().setPassword('foo');
  ob.signup().selectCreateAccount();
  util.screenCapture('signup_form_password_short');
  util.dismissAlert("OK");
  // Cancel sign up.
  assertTrue(ob.signup().selectCancel(),"Selected Cancel button.");

  // Bring sign up form back up.
  assertTrue(ob.gotoSignup(),"At signup form.");

  // Set good password.

  log.debug("------------------------------------");
  log.debug("Sign up: Fix password and sign up.");
  log.debug("------------------------------------");

  ob.signup().setPassword(t.password);
  ob.signup().selectCreateAccount();

  util.screenCapture('created_account');

  log.debug("------------------------------------");
  log.debug("Sign up: Get access code and enter it in form... Exit.");
  log.debug("------------------------------------");
  var access_code = user.get_access_code('Email:' + t.email);
  ob.signup().setAccessCode(access_code);

  // Confirm your account: exit
  ob.signup().selectExit();

  log.debug("------------------------------------");
  log.debug("Sign up:  Enter 3-digit access code.");
  log.debug("------------------------------------");
  ob.signup().selectCreateAccount();
  target.delay(4); // TODO: replace delay
  ob.signup().setAccessCode('987');

  ob.signup().selectContinue();
  util.screenCapture('access_code_too_short');
  util.dismissAlert("OK");

  log.debug("------------------------------------");
  log.debug("Sign up:  Send code again.");
  log.debug("------------------------------------");
  ob.signup().selectSendCodeAgain();
  var access_code = user.get_access_code('Email:' + t.email);

  log.debug("------------------------------------");
  log.debug("Sign up:  Enter correct access code.");
  log.debug("------------------------------------");
  ob.signup().setAccessCode(access_code);

  ob.signup().selectContinue();
  target.delay(2); // for accurate screen shot
  util.screenCapture('logged_in_dashboard');





});
