/**
 * Wrapper to run unit tests
 * @class VFRunTest
 * @constructor
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @author: Greg Vandenberg
 *
 */
var VFRunTest = function (_testName, _runState, runTestFunc) {
  var testName = _testName;
  var nav = new VFNavigation();
  var util = new VFUtils(nav, _testName);
  var log = new VFLogger();

  UIATarget.onAlert = function onAlert(alert){
    /**
     * By returning true, you are notifying the framework that
     * you will handle the alert and bypass the default handler.
     */
    return true;
  }

  /**
   * Need to determine that the VF application
   * has started successfully before test starts
   */
  try {
    util.pollUntilButtonVisible(BUTTON_SIGNUP, 'main_window', 10);
    log.start(testName);
    util.setupCleanStateAll(_runState);
    runTestFunc(testName, util, log);
    log.pass(testName);
  }
  catch(err) {
    throw new Exception(err.stack);
  }

}


