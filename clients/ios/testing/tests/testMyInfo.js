/**
 *
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: From logged in on the dashboard, merge and link
 * identities to your account
 * @author: Greg Vandenberg
 *
 */

VFRunTest("testMyInfo", runStateEnum.DASHBOARD, function(testname, util, log) {

  var t = TEST_USERS[0];
  var t5 = TEST_USERS[4];
  var user = new VFUser();
  var dash = util.gotoDashboard();
  var info = dash.gotoMyInfo();

  info.selectAddEmailOrMobile();

  log.debug("------------------------------------");
  log.debug("MyInfo: Incorrect email format.");
  log.debug("------------------------------------");
  info.setEmailAddress('tester');

  info.selectAdd();
  target.delay(2); // TODO: poll instead
  util.screenCapture('email_is_incorrect_format');
  util.dismissAlert("Let me fix that...");

  log.debug("------------------------------------");
  log.debug("MyInfo: Email already linked.");
  log.debug("------------------------------------");
  info.setEmailAddress(t.email);

  info.selectAdd();

  util.screenCapture('email_is_already_linked');
  util.dismissAlert("OK");

  log.debug("------------------------------------");
  log.debug("MyInfo: Link email.");
  log.debug("------------------------------------");
  info.setEmailAddress(t5.email);

  info.selectAdd();
  //util.delay(2); // TODO:  retry in get_access_code method
  var access_code = user.get_access_code('Email:' + t5.email);
  util.delay(2);
  info.setAccessCode(access_code);

  info.selectContinue();
  util.delay(2); // wait for merge ui to settle
  util.screenCapture('merged_or_linked_account');

  info.selectAddEmailOrMobile();

  log.debug("------------------------------------");
  log.debug("MyInfo: Link mobile number.");
  log.debug("------------------------------------");
  info.setMobileNumber(t5.mobile);

  info.selectAdd();
  //util.delay(2);  // TODO:  retry in get_access_code method
  var access_code2 = user.get_access_code('Phone:' + t5.mobile);

  info.setAccessCode(access_code2);

  info.selectContinue();
  util.delay(2); // wait for merge ui to settle
  util.screenCapture('merged_or_linked_number');

});
