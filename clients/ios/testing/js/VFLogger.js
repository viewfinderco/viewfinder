/**
 * The utility class for logging
 * @class VFLogger
 * @copyright 2013 Viewfinder Inc. All Rights Reserved.
 * @description: Log to stdout.
 * @author: Greg Vandenberg
 *
 */
var VFLogger = function () {

  return {
    /**
     * @method pass
     * @param {string} message
     */
    pass: function(message) {
      UIALogger.logMessage('===============================================');
      UIALogger.logPass(message);
      UIALogger.logMessage('===============================================');
    },
    /**
     * @method start
     * @param {string} message
     */
    start: function(message) {
      UIALogger.logMessage('===============================================');
      UIALogger.logStart(message);
      UIALogger.logMessage('===============================================');
    },
    /**
     * @method debug
     * @param {string} message
     */
    debug: function(message) {
      UIALogger.logDebug(message);
    },
    /**
     * @method error
     * @param {string} message
     * @throws Exception(message)
     */
    error: function(message) {
      UIALogger.logDebug(message);
      UIALogger.logError(message);
      throw new Exception(message);
    }
  }
};
