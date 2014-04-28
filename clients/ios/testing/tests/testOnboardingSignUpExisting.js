/**
 *
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: From an unlinked state, login with new user (terminated) and
 * an existing user
 * @author: Greg Vandenberg
 *
 */

VFRunTest("testOnboardingSignUpExisting", runStateEnum.ONBOARDING, function(testname, util, log) {

  var ob = new VFOnboarding(util.getNav());
  var t = TEST_USERS[0];
  var user = new VFUser();
  user.register(t);

  log.debug("------------------------------------");
  log.debug("Start Signup process (existing user).");
  log.debug("------------------------------------");

  ob.gotoSignup();
  util.screenCapture('signup_form2');

  ob.signup().setFirstName(t.firstname);
  ob.signup().setLastName(t.lastname);
  ob.signup().setValidEmailFormat(t.email);
  ob.signup().setPassword(t.password);

  util.screenCapture('signup_form_filled_out2');

  ob.signup().selectCreateAccount();

  util.screenCapture('created_account_existing');
  util.dismissAlert("OK");

  ob.login().selectLogin();
});
