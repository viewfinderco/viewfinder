// Copyright 2013 Viewfinder. All rights reserved.
// Author: Andy Kimball
package co.viewfinder;

import android.widget.TextView;

/**
 * Collection of utility methods to validate user input and report errors.
 */
public class InputValidation {
  public static boolean setHintIfEmpty(TextView textView, int errorTextId) {
    if (textView.getText().length() == 0) {
      textView.setHint(errorTextId);
      return false;
    }

    return true;
  }
}
