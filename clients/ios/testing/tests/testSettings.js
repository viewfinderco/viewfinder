/**
 *
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: Check all settings
 * @author: Greg Vandenberg
 *
 */
VFRunTest("testSettings", runStateEnum.DASHBOARD, function(testname, util, log) {
  var dash = util.gotoDashboard();

  log.debug("------------------------------------");
  log.debug("Show initial Setting screen.");
  log.debug("------------------------------------");
  var settings = dash.gotoSettings();
  util.screenCapture('settings_screen');

  settings.selectStorage('local');

  log.debug("------------------------------------");
  log.debug("Select lowest option on picker.");
  log.debug("------------------------------------");
  settings.selectLowestPickerOption();
  util.screenCapture('Lowest_Picker_Option');

  settings.selectStorage('local');

  log.debug("------------------------------------");
  log.debug("Turn off Cloud Storage.");
  log.debug("------------------------------------");
  settings.selectStorage('cloud');

  //settings.selectViewfinderPlus();
  //util.screenCapture('viewfinder_plus_option');
  //target.frontMostApp().windows()[0].tableViews()["Empty list"].cells()["Cloud Storage, 1 GB"].tap();
  //target.frontMostApp().windows()[0].tableViews()["Empty list"].cells()["5 GB, Viewfinder Plus, $1.99 / month"].tap();

  settings.selectCloudStorage(1);
  util.screenCapture('cloud_storage_on');

  settings.selectCloudStorage(0);
  util.screenCapture('cloud_storage_off');

  util.selectBackNav();

  // TODO: add buy flow
  //target.frontMostApp().windows()[0].navigationBar().buttons()["Buy"].tap();
  //util.waitUntilVisible(SETTINGS_PAGE_FAQ, 5);

  log.debug("------------------------------------");
  log.debug("Goto FAQ.");
  log.debug("------------------------------------");
  settings.selectSubPage(SETTINGS_PAGE_FAQ);
  target.delay(3); // TODO: poll instead
  util.screenCapture('FAQ');
  settings.selectBackNav();

  log.debug("------------------------------------");
  log.debug("Goto Feedback.");
  log.debug("------------------------------------");
  settings.selectSubPage(SETTINGS_PAGE_FEEDBACK);
  target.delay(3); // TODO: poll instead
  util.screenCapture('feedback_email');
  util.selectBackNav();
  settings.selectDeleteDraft();

  log.debug("------------------------------------");
  log.debug("Goto Terms of Service.");
  log.debug("------------------------------------");
  settings.selectSubPage(SETTINGS_PAGE_TOS);
  target.delay(3); // TODO: poll instead
  util.screenCapture('TOS');
  settings.selectBackNav();

  log.debug("------------------------------------");
  log.debug("Goto Privacy Policy.");
  log.debug("------------------------------------");
  settings.selectSubPage(SETTINGS_PAGE_PRIVACY);
  util.screenCapture('privacy_policy');
  settings.selectBackNav();




});
