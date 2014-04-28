/**
 *
 * Copyright 2013 Viewfinder Inc. All Rights Reserved.
 * Description: Export photos, error on none selected starting from the dashboard.
 * Author: Greg Vandenberg
 *
 */

VFRunTest("testExportPhotos", runStateEnum.DASHBOARD, function(testname, util, log) {

  var dash = new VFDashboard();
  var user = new VFUser();
  var t = TEST_USERS[1];

  log.debug("------------------------------------");
  log.debug("Go to Library.");
  log.debug("------------------------------------");
  var library = dash.gotoLibrary();
  target.delay(2); // for accurate screen shot
  util.screenCapture('personal_library');

  log.debug("------------------------------------");
  log.debug("Export 5 photos to camera roll.");
  log.debug("------------------------------------");
  library.selectActionButton();
  target.delay(2); // for accurate screen shot
  util.screenCapture('library_action');

  library.selectNumImages(5);

  library.selectExportButton();
  target.delay(2); // for accurate screen shot
  util.screenCapture('export_button_5_photos');

  library.selectConfirmExport();

  log.debug("------------------------------------");
  log.debug("Go back to dashboard.");
  log.debug("------------------------------------");
  util.gotoDashboard();
  util.screenCapture('dashboard');

  log.debug("------------------------------------");
  log.debug("Go to library.");
  log.debug("------------------------------------");
  library = dash.gotoLibrary();

  log.debug("------------------------------------");
  log.debug("Export 1 photo to camera roll.");
  log.debug("------------------------------------");
  library.selectActionButton();
  library.selectNumImages(1);

  library.selectExportButton();
  util.screenCapture('export_button_1_photo');

  library.selectConfirmExport();

  log.debug("------------------------------------");
  log.debug("Go back to dashboard.");
  log.debug("------------------------------------");
  util.gotoDashboard();

});
