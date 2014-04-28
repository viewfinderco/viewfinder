// Copyright 2013 Viewfinder. All rights reserved.
// Author: Andy Kimball
package co.viewfinder;

import android.app.AlertDialog;
import android.content.Context;
import co.viewfinder.proto.ServerPB;
import junit.framework.Assert;

/**
 */
public class ErrorDialogManager {
  private Context mContext;

  public ErrorDialogManager(Context context) {
    mContext = context;
  }

  public void show(int errorId, Object... formatArgs) {
    show(mContext.getResources().getString(errorId), formatArgs);
  }

  public void show(int statusCode, ServerPB.ErrorResponse error) {
    Assert.assertNotNull(error);
    show(R.string.error_server, error.getError().getText());
  }

  public void show(String errorText, Object... formatArgs) {
    String title = null;
    String message = null;
    String button = null;

    if (formatArgs.length > 0) {
      errorText = String.format(errorText, formatArgs);
    }

    errorText = errorText.trim();

    // Title is first line of text.
    int titleEnd = errorText.indexOf('\n');
    Assert.assertTrue(titleEnd != -1);
    title = errorText.substring(0, titleEnd).trim();

    // Button is last line of text.
    int buttonStart = errorText.lastIndexOf('\n');
    Assert.assertTrue(buttonStart != -1);
    button = errorText.substring(buttonStart + 1).trim();

    // Message is everything else.
    Assert.assertTrue(titleEnd != buttonStart);
    message = errorText.substring(titleEnd + 1, buttonStart).trim();

    AlertDialog.Builder builder = new AlertDialog.Builder(mContext);
    builder.setTitle(title);
    builder.setMessage(message);
    builder.setPositiveButton(button, null);
    builder.create().show();
  }
}
