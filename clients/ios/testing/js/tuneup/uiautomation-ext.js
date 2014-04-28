//#import "assertions.js"
//#import "lang-ext.js"

extend(UIATableView.prototype, {
  /**
   * A shortcut for:
   *  this.cells().firstWithName(name)
   */
  cellNamed: function(name) {
    return this.cells().firstWithName(name);
  },

  /**
   * Asserts that this table has a cell with the name (accessibility label)
   * matching the given +name+ argument.
   */
  assertCellNamed: function(name) {
    assertNotNull(this.cellNamed(name), "No table cell found named '" + name + "'");
  }
});

extend(UIAElement.prototype, {
	/**
	 * Poll till the item becomes visible, up to a specified timeout
	 */
	waitUntilVisible: function (timeoutInSeconds) {
        this.waitUntil(function(element) {
            return element;
        }, function(element) {
            return element.isVisible();
        }, timeoutInSeconds, "to become visible");
	},

	/**
	 * Wait until element becomes invisible
	 */
	waitUntilInvisible: function (timeoutInSeconds) {
        this.waitUntil(function(element) {
            return element;
        }, function(element) {
            return !element.isVisible();
        }, timeoutInSeconds, "to become invisible");
    },

    /**
     * Wait until child element with name is added
     */
    waitUntilFoundByName: function (name, timeoutInSeconds) {
        this.waitUntil(function(element) {
            return element.elements().firstWithName(name);
        }, function(element) {
            return element.isValid();
        }, timeoutInSeconds, "to become valid");
    },

    /**
     * Wait until child element with name is removed
     */
    waitUntilNotFoundByName: function (name, timeoutInSeconds) {
        this.waitUntil(function(element) {
            return element.elements().firstWithName(name);
        }, function(element) {
            return !element.isValid();
        }, timeoutInSeconds, "to become invalid");
    },

    /**
     * Wait until element fulfills condition
     */
    waitUntil: function (filterFunction, conditionFunction, timeoutInSeconds, description) {
        timeoutInSeconds = timeoutInSeconds == null ? 5 : timeoutInSeconds;
        var element = this;
        var delay = 0.25;
        retry(function() {
          var filteredElement = filterFunction(element);
          if(!conditionFunction(filteredElement)) {
            throw(["Element", filteredElement, "failed", description, "within", timeoutInSeconds, "seconds."].join(" "));
          }
        }, Math.max(1, timeoutInSeconds/delay), delay);
    },



});



extend(UIAButton.prototype, {
  /**
   * A shortcut for waiting an element to become visible and tap.
   */
  vtap: function() {
    this.waitUntilVisible(10);
    this.tap();
  },
  /**
   * A shortcut for touching an element and waiting for it to disappear.
   */
  tapAndWaitForInvalid: function() {
    this.tap();
    this.waitForInvalid();
  }
});

extend(UIAApplication.prototype, {
  /**
   * A shortcut for getting the current view controller's title from the
   * navigation bar. If there is no navigation bar, this method returns null
   */
  navigationTitle: function() {
    navBar = this.mainWindow().navigationBar();
    if (navBar) {
      return navBar.name();
    }
    return null;
  },
  /**
   * Make the conversion from hitpoint to relative position within window
   */
  tapHitPoint: function(hitpoint) {
	  var rect = this.windows()[0].rect();
	  var x_offset = (hitpoint.x / rect.size.width).toFixed(2);
	  var y_offset = (hitpoint.y / rect.size.height).toFixed(2);
	  var offset = {tapOffset:{x:x_offset, y:y_offset}};
	  this.tapWithOptions(offset);
  },

  /**
   * A shortcut for checking that the interface orientation in either
   * portrait mode
   */
  isPortraitOrientation: function() {
    var orientation = this.interfaceOrientation();
    return orientation == UIA_DEVICE_ORIENTATION_PORTRAIT ||
      orientation == UIA_DEVICE_ORIENTATION_PORTRAIT_UPSIDEDOWN;
  },

  /**
   * A shortcut for checking that the interface orientation in one of the
   * landscape orientations.
   */
  isLandscapeOrientation: function() {
    var orientation = this.interfaceOrientation();
    return orientation == UIA_DEVICE_ORIENTATION_LANDSCAPELEFT ||
      orientation == UIA_DEVICE_ORIENTATION_LANDSCAPERIGHT;
  }
});

extend(UIANavigationBar.prototype, {
  /**
   * Asserts that the left button's name matches the given +name+ argument
   */
  assertLeftButtonNamed: function(name) {
    assertEquals(name, this.leftButton().name());
  },

  /**
   * Asserts that the right button's name matches the given +name+ argument
   */
  assertRightButtonNamed: function(name) {
    assertEquals(name, this.rightButton().name());
  }
});

extend(UIATarget.prototype, {
  /**
   * A shortcut for checking that the interface orientation in either
   * portrait mode
   */
  isPortraitOrientation: function() {
    var orientation = this.deviceOrientation();
    return orientation == UIA_DEVICE_ORIENTATION_PORTRAIT ||
      orientation == UIA_DEVICE_ORIENTATION_PORTRAIT_UPSIDEDOWN;
   },

  /**
   * A shortcut for checking that the interface orientation in one of the
   * landscape orientations.
   */
  isLandscapeOrientation: function() {
    var orientation = this.deviceOrientation();
    return orientation == UIA_DEVICE_ORIENTATION_LANDSCAPELEFT ||
      orientation == UIA_DEVICE_ORIENTATION_LANDSCAPERIGHT;
   },

   /**
    * A convenience method for detecting that you're running on an iPad
    */
    isDeviceiPad: function() {
      //model is iPhone Simulator, even when running in iPad mode
      return this.model().match(/^iPad/) !== null ||
        this.name().match(/iPad Simulator/) !== null;
    },

    /**
     * A convenience method for detecting that you're running on an
     * iPhone or iPod touch
     */
    isDeviceiPhone: function() {
      return this.model().match(/^iPad/) === null &&
        this.name().match(/^iPad Simulator$/) === null;
    },

    /**
     * A shortcut for checking if target device is iPhone 5 (or iPod Touch
     * 5th generation)
     */
  	isDeviceiPhone5: function() {
  		var isIphone = this.isDeviceiPhone();
  		var deviceScreen = this.rect();
      	return isIphone && deviceScreen.size.height == 568;
     },

    /**
     * A convenience method for producing screenshots without status bar
     */
    captureAppScreenWithName: function(imageName) {
      var appRect = this.rect();

      appRect.origin.y     += 20.0;
      appRect.size.height  -= 20.0;

      return this.captureRectWithName(appRect, imageName);
    },
    main: function() {
      var main = UIATarget.localTarget().frontMostApp().windows()[0];

      if (this.isDeviceiPad()) {
        main = UIATarget.localTarget().frontMostApp().windows()[1];
      }
      return main;
    },
    app: function() {
      return UIATarget.localTarget().frontMostApp();
    }

});

extend(UIAKeyboard.prototype,{
  KEYBOARD_TYPE_UNKNOWN :-1,
  KEYBOARD_TYPE_ALPHA : 0,
  KEYBOARD_TYPE_ALPHA_CAPS : 1,
  KEYBOARD_TYPE_NUMBER_AND_PUNCTUATION:2,
  KEYBOARD_TYPE_NUMBER:3,
  keyboardType : function() {
  if (this.keys().length < 12){
    return this.KEYBOARD_TYPE_NUMBER;
  } else if (this.keys().firstWithName("a").toString() != "[object UIAElementNil]") {
    return this.KEYBOARD_TYPE_ALPHA;
  } else if (this.keys().firstWithName("A").toString() != "[object UIAElementNil]") {
    return this.KEYBOARD_TYPE_ALPHA_CAPS;
  } else if (this.keys().firstWithName("1").toString() != "[object UIAElementNil]") {
    return this.KEYBOARD_TYPE_NUMBER_AND_PUNCTUATION;
  } else {
    return this.KEYBOARD_TYPE_UNKNOWN;
  }
  }
});

/**
 * determine the specified object's type
 *
 * @method type
 * @param {object} obj
 * @return {string}
 */
var type = function(obj) {
  return Object.prototype.toString.call(obj).match(/^\[object (.*)\]$/)[1];
}
/*
TODO: Character keyboard is super slow.
*/
var typeString = function(pstrString, pbClear) {
  pstrString += ''; // convert number to string
  UIALogger.logDebug("Has focus? " + this.hasKeyboardFocus());
  if (!this.hasKeyboardFocus()){
    this.tap();
  }

  UIATarget.localTarget().delay(0.5);

  if (pbClear || pstrString.length === 0) {
    //this.clear();
    var btn_clear = this.buttons()["Clear text"];
    UIALogger.logDebug("Clear button: " + type(btn_clear));
    if (type(btn_clear) != 'UIAElementNil') {
      if (UIATarget.localTarget().isDeviceiPad()) {
        this.setValue("");
      }
      else {
        btn_clear.vtap();
      }
    }
  }

  if (pstrString.length > 0) {
    // TODO: figure out why 1X iPad keyboard is not visible to UIAutomation
    if (UIATarget.localTarget().isDeviceiPad()) {
      this.setValue(pstrString);
    }
    else {
      var app = UIATarget.localTarget().frontMostApp();
      var keyboard = app.keyboard();
      keyboard.typeString(pstrString);
    }

  }
};

extend(UIATextField.prototype,{
  typeString: typeString
});
extend(UIATextView.prototype,{
	typeString: typeString
});
extend(UIATableCell.prototype,{
  typeString: typeString
});

extend(UIAPickerWheel.prototype, {

   /*
    * Better implementation than UIAPickerWheel.selectValue
    * Works also for texts
    * Poorly works not for UIDatePickers -> because .values() which get all values of wheel does not work :(
    * I think this is a bug in UIAutomation!
    */
   scrollToValue: function (valueToSelect) {

      var element = this;

      var values = this.values();
      var pickerValue = element.value();

      // convert to string
      valueToSelect = valueToSelect + "";

      // some wheels return for .value()  "17. 128 of 267" ?? don't know why
      // throw away all after "." but be careful lastIndexOf is used because the value can
      // also have "." in it!! e.g.: "1.2. 13 of 27"
      if (pickerValue.lastIndexOf(".") != -1) {
        var currentValue = pickerValue.substr(0, pickerValue.lastIndexOf("."));
      } else {
        var currentValue = element.value();
      }

      var currentValueIndex = values.indexOf(currentValue);
      var valueToSelectIndex = values.indexOf(valueToSelect);

      if (valueToSelectIndex == -1) {
        fail("value: " + valueToSelect + " not found in Wheel!");
      }

      var elementsToScroll = valueToSelectIndex - currentValueIndex;

      UIALogger.logDebug("number of elements to scroll: " + elementsToScroll);
      if (elementsToScroll > 0) {

          for (i=0; i<elementsToScroll; i++) {
            element.tapWithOptions({tapOffset:{x:0.35, y:0.67}});
            target.delay(0.7);
          }

      } else {

          for (i=0; i>elementsToScroll; i--) {
            element.tapWithOptions({tapOffset:{x:0.35, y:0.31}});
            target.delay(0.7);
          }
      }
   },

   /*
    * Wheels filled with values return for .value()  "17. 128 of 267" ?? don't know why -> for comparisons this is not useful!!
    * If you want to check a value of a wheel this function is very helpful
    */
   realValue: function() {

      // current value of wheel
      var pickerValue = this.value();

      // throw away all after "." but be careful lastIndexOf is used because the value can
      if (pickerValue.lastIndexOf(".") != -1) {
        return pickerValue.substr(0, pickerValue.lastIndexOf("."));
      }

      return this.value();
   }
});
