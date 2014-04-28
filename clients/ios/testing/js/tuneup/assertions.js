/**
 * The exception thrown when a 'fail' is used.
 *
 * @param message - reason the test failed/aborted
 */
function FailureException(message) {
    this.name = 'FailureException';
    this.message = message;
    this.toString = function() {
        return this.name + ': "' + this.message + '"';
    };
}

/**
 * Just flat-out fail the test with the given message
 */
function fail(message) {
  throw new FailureException(message);
}

/**
 * Perform an assertion several times. If the assertion passes before the
 * maximum number of iterations, the assertion passes. Otherwise the
 * assertion fails
 * @param f The function to perform (possibly) multiple times
 * @param maxTries (optional) The maximum number of attempts
 * @param delay (optional) The amount of time to pause between attempts
 */
function retry() {
  var f = arguments[0];
  var maxTries = 3;
  var delay = 0.5;
  if (arguments.length > 1) {
    maxTries = arguments[1];
  }
  if (arguments.length > 2) {
    delay = arguments[2];
  }

  var tries = 0;
  var exception = null;
  while (tries < maxTries) {
    try {
      f();
      return;  // if we get here, our function must have passed (no exceptions)
    }
    catch(e) {
      exception = e;
      tries++;
      UIATarget.localTarget().delay(delay);
    }
  }
  throw exception;
}

/**
 * The exception thrown for all assert* failures.
 *
 * @param message - reason the assertion failed
 */
function AssertionException(message) {
    this.name = 'AssertionException';
    this.message = message;
    this.toString = function() {
        return this.name + ': "' + this.message + '"';
    };
}

/**
 * Asserts that the given expression is true and throws an exception with
 * a default message, or the optional +message+ parameter
 */
function assertTrue(expression, message) {
  if (! expression) {
    if (! message) {
      message = "Assertion failed";
    }
    throw new AssertionException("Failed: " + message);
  }
  else {
	  UIALogger.logDebug("AssertTrue: " + message);
  }
}

/**
 * Asserts that the given regular expression matches the result of the
 * given message.
 * @param pattern - the pattern to match
 * @param expression - the expression to match against
 * @param message - an optional string message
 */
function assertMatch(regExp, expression, message) {
  var defMessage = "'" + expression + "' does not match '" + regExp + "'";
  assertTrue(regExp.test(expression), message ? message + ": " + defMessage : defMessage);
}

/**
 * Assert that the +received+ object matches the +expected+ object (using
 * plain ol' ==). If it doesn't, this method throws an exception with either
 * a default message, or the one given as the last (optional) argument
 */
function assertEquals(expected, received, message) {
  var defMessage = "Expected <" + expected + "> but received <" + received + ">";
  assertTrue(expected == received, message ? message + ": " + defMessage : defMessage);
}

/**
 * Assert that the +received+ object does not matches the +expected+ object (using
 * plain ol' !=). If it doesn't, this method throws an exception with either
 * a default message, or the one given as the last (optional) argument
 */
function assertNotEquals(expected, received, message) {
    var defMessage = "Expected not <" + expected + "> but received <" + received + ">";
    assertTrue(expected != received, message ? message + ": " + defMessage : defMessage);
}

/**
 * Asserts that the given expression is false and otherwise throws an
 * exception with a default message, or the optional +message+ parameter
 */
function assertFalse(expression, message) {
  assertTrue(! expression, message);
}

/**
 * Asserts that the given object is null or UIAElementNil (UIAutomation's
 * version of a null stand-in). If the given object is not one of these,
 * an exception is thrown with a default message or the given optional
 * +message+ parameter.
 */
function assertNull(thingie, message) {
  var defMessage = "Expected a null object, but received <" + thingie + ">";
  // TODO: string-matching on UIAElementNil makes my tummy feel bad. Fix it.
  assertTrue(thingie === null || thingie.toString() == "[object UIAElementNil]",
    message ? message + ": " + defMessage : defMessage);
}

/**
 * Asserts that the given object is not null or UIAElementNil (UIAutomation's
 * version of a null stand-in). If it is null, an exception is thrown with
 * a default message or the given optional +message+ parameter
 */
function assertNotNull(thingie, message) {
  var defMessage = "Expected not null object";
  assertTrue(thingie !== null && thingie.toString() != "[object UIAElementNil]",
    message ? message + ": " + defMessage : defMessage);
}

function OnPassException(message) {
    this.name = 'OnPassException';
    this.message = message;
    this.toString = function() {
        return this.name + ': "' + this.message + '"';
    };
}

/**
 * Assert that the given definition matches the given element. The
 * definition is a JavaScript object whose property hierarchy matches
 * the given UIAElement.  Property names in the given definition that match a
 * method will cause that method to be invoked and the matching to be performed
 * and the result. For example, the UITableView exposes all UITableViewCells through
 * the cells() method. You only need to specify a 'cells' property to
 * cause the method to be invoked.
 */
function assertElementTree(element, definition) {
  var onPass = null;
  if (definition.onPass) {
    onPass = definition.onPass;
    delete definition.onPass;
  }

  try {
    assertPropertiesMatch(definition, element, 0);
  }
  catch(badProp) {
    fail("Failed to match " + badProp[0] + ": " + badProp[1]);
  }

  if (onPass) {
    try {
      onPass(element);
    }
    catch(e) {
      throw new OnPassException("Failed to execute 'onPass' callback: " + e);
    }
  }
}

/**
 * Assert that the given window definition matches the current main window. The
 * window definition is a JavaScript object whose property hierarchy matches
 * the main UIAWindow.  Property names in the given definition that match a
 * method will cause that method to be invoked and the matching to be performed
 * and the result. For example, the UIAWindow exposes all UITableViews through
 * the tableViews() method. You only need to specify a 'tableViews' property to
 * cause the method to be invoked.
 *
 * PROPERTY HIERARCHY Property definitions can be nested as deeply as
 * necessary. Matching is done by traversing the same path in the main
 * UIAWindow as your screen definition. For example, to make assertions about
 * the left and right buttons in a UINavigationBar you can do this:
 *
 * assertWindow({
 *   navigationBar: {
 *     leftButton: { name: "Back" },
 *     rightButton: ( name: "Done" },
 *   }
 * });
 *
 * PROPERTY MATCHERS For each property you wish to make an assertion about, you
 * can specify a string, number regular expression or function. Strings and
 * numbers are matches using the assertEquals() method. Regular expressions are
 * matches using the assertMatch() method.
 *
 * If you specify 'null' for a property, it means you don't care to match.
 * Typically this is done inside of arrays where you need to match the number
 * of elements, but don't necessarily care to make assertions about each one.
 *
 * Functions are given the matching property as the single argument. For
 * example:
 *
 * assertWindow({
 *   navigationBar: {
 *     leftButton: function(button) {
 *       // make custom assertions here
 *     }
 *   }
 * });
 *
 * ARRAYS
 * If a property you want to match is an array (e.g. tableViews()), you can
 * specify one of the above matchers for each element of the array. If the
 * number of provided matchers does not match the number of given elements, the
 * assertion will fail (throw an exception)
 *
 * In any case, you specify another object definition for each property to
 * drill-down into the atomic properties you wish to test. For example:
 *
 * assertWindow({
 *   navigationBar: {
 *     leftButton: { name: "Back" },
 *     rightButton: ( name: "Done" },
 *   },
 *   tableViews: [
 *     {
 *       groups: [
 *         { name: "First Group" },
 *         { name: "Second Group" }
 *       ],
 *       cells: [
 *         { name: "Cell 1" },
 *         { name: "Cell 2" },
 *         { name: "Cell 3" },
 *         { name: "Cell 4" }
 *       ]
 *     }
 *   ]
 * });
 *
 * HANDLING FAILURE If any match fails, an appropriate exception will be
 * thrown. If you are using the test structure provided by tuneup, this will be
 * caught and detailed correctly in Instruments.
 *
 * POST-PROCESSING If your screen definition provides an 'onPass' property that
 * points to a function, that function will be invoked after all matching has
 * been peformed on the current window and all assertions have passed. This
 * means you can assert the structure of your screen and operate on it in one
 * pass:
 *
 * assertWindow({
 *   navigationBar: {
 *     leftButton: { name: "Back" }
 *   },
 *   onPass: function(window) {
 *     var leftButton = window.navigationBar().leftButton();
 *     leftButton.tap();
 *   }
 * });
 */
function assertWindow(window) {
  target = UIATarget.localTarget();
  application = target.frontMostApp();
  mainWindow = application.mainWindow();

  assertElementTree(mainWindow, window);
}

/**
 * Asserts that the +expected+ object matches the +given+ object by making
 * assertions appropriate based on the pe of each property in the
 * +expected+ object. This method will recurse through the structure,
 * applying assertions for each matching property path. See the description
 * for +assertWindow+ for details on the matchers.
 */
function assertPropertiesMatch(expected, given, level) {
  for (var propName in expected) {
    if (expected.hasOwnProperty(propName)) {
      var expectedProp = expected[propName];

      if (propName.match(/~iphone$/)) {
        if (UIATarget.localTarget().model().match(/^iPad/) !== null ||
            UIATarget.localTarget().name().match(/^iPad Simulator$/) !== null) {
          continue;  // we're on the wrong platform, ignore
        } else {
          propName = propName.match(/^(.*)~iphone/)[1];
        }
      } else if (propName.match(/~ipad$/)) {
        if (UIATarget.localTarget().model().match(/^iPad/) === null &&
            UIATarget.localTarget().name().match(/^iPad Simulator/) === null) {
          continue;  // we're on the wrong platform, ignore
        } else {
          propName = propName.match(/^(.*)~ipad/)[1];
        }
      }

      var givenProp = given[propName];

      if (typeof(givenProp) == "function") {
        try {
          // We have to use eval (shudder) because calling functions on
          // UIAutomation objects with () operator crashes
          // See Radar bug 8496138
          givenProp = eval("given." + propName + "()");
        }
        catch (e) {
          UIALogger.logError("[" + propName + "]: Unable to evaluate against " + given);
          continue;
        }
      }

      if (givenProp === null) {
          throw new AssertionException("Could not find given " + given + " property named: " + propName);
      }

      try {
        // null indicates we don't care to match
        if (expectedProp === null) {
          continue;
        }

        var expectedPropType = typeof(expectedProp);
        if (expectedPropType == "string") {
          assertEquals(expectedProp, givenProp);
        } else if (expectedPropType == "number") {
          assertEquals(expectedProp, givenProp);
        } else if (expectedPropType == "function") {
          if (expectedProp.constructor == RegExp) {
            assertMatch(expectedProp, givenProp);
          } else {
            expectedProp(givenProp);
          }
        } else if (expectedPropType == "object") {
          if (expectedProp.constructor === Array) {
            var expectedPropLength = expectedProp.length;
            for (var i = 0; i < expectedPropLength; i++) {
              var exp = expectedProp[i];
              var giv = givenProp[i];
              assertPropertiesMatch(exp, giv, level + 1);
            }
          } else if (expectedProp.constructor === RegExp) {
            assertMatch(expectedProp, givenProp);
          } else if (typeof(givenProp) == "object") {
            assertPropertiesMatch(expectedProp, givenProp, level + 1);
          } else {
            var message = "[" + propName + "]: Unknown type of object constructor: " + expectedProp.constructor;
            UIALogger.logError(message);
            throw new AssertionException(message);
          }
        } else {
          UIALogger.logError("[" + propName + "]: unknown type for expectedProp: " + typeof(expectedProp));
        }
      }
      catch(e1) {
        UIALogger.logError("Got an exception: " + e1);
        if (e1.constructor == Array) {
          e1[0] = propName + "." + e1[0];
          throw e1;
        }
        else {
          var err = [propName, e1];
          throw err;
        }
      }
    }
  }
}

