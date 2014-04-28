// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.support.v4.app.FragmentActivity;
import android.util.Log;
import android.view.View;
import android.view.WindowManager;
import android.view.inputmethod.InputMethodManager;
import android.widget.TextView;

import java.util.Observable;
import java.util.Observer;

/**
 * Contains functionality common to most or all Activities.
 */
public class BaseActivity extends FragmentActivity implements Observer {
  private static final String TAG = "Viewfinder.BaseActivity";
  private static int mActiveActivityCount;
  private static CustomActivityTransition mPendingTransition;

  private TextView mTextViewStatus;
  private ErrorDialogManager mErrorDialogManager;
  private CustomActivityTransition mCustomTransition;

  protected BaseActivity() {
    mErrorDialogManager = new ErrorDialogManager(this);
  }

  protected AppState getAppState() { return (AppState) getApplication(); }
  protected NetworkManager getNetworkManager() { return getAppState().networkManager(); }

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);

    // All layout should be done assuming Android status bar is NOT present.
    getWindow().addFlags(WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS);

    // Remember the custom transition specified by the calling activity, if it exists.
    mCustomTransition = mPendingTransition;
    mPendingTransition = null;
  }

  public ErrorDialogManager getErrorDialogManager() {
    return mErrorDialogManager;
  }

  /**
   * Set a custom transition to use when switching to the next activity.
   *
   * See the header for CustomActivityTransition for more details.
   */
  public void overridePendingTransition(CustomActivityTransition customTransition) {
    // Remember the custom transition in a static variable so that next activity can get it.
    mPendingTransition = customTransition;
  }

  @Override
  public void startActivity(Intent intent) {
    super.startActivity(intent);

    // Suppress default Android transition animations.
    overridePendingTransition(0, 0);
  }

  @Override
  public void onAttachedToWindow() {
    super.onAttachedToWindow();

    // If a custom activity transition exists, transition forward to this activity.
    if (mCustomTransition != null) {
      // Clear any system transition.
      super.overridePendingTransition(0, 0);

      mCustomTransition.transition(this, true /* isForward */, null);
    }
  }

  @Override
  public void onBackPressed() {
    // If a custom activity transition exists and there are no fragments on the backstack,
    // transition backward from this activity to the parent activity.
    if (mCustomTransition != null && getSupportFragmentManager().getBackStackEntryCount() == 0) {
      mCustomTransition.transition(this, false /* isForward */, new CustomActivityTransition.CompletionListener() {
        @Override
        public void onCompletion() {
          // Now that transition is complete, finish the back action.
          BaseActivity.super.onBackPressed();
          overridePendingTransition(0, 0);
        }
      });
    } else {
      super.onBackPressed();

      // Suppress default Android transition animations.
      overridePendingTransition(0, 0);
    }
  }

  @Override
  protected void onStart() {
    super.onStart();
    mActiveActivityCount++;
  }

  @Override
  protected void onStop() {
    super.onStop();
    mActiveActivityCount--;

    if (0 == mActiveActivityCount) {
      Log.d(TAG, "onStop(): no active activities.  Evicting all from caches.");
      getAppState().bitmapFetcher().evictAllFromCache();
    }
  }

  @Override
  protected void onResume() {
    super.onResume();

    mTextViewStatus = (TextView)findViewById(R.id.statusbar_text);
    if (mTextViewStatus != null) {
      // Set the text view height to be the status bar height.
      int statusBarHeight = getAppState().getStatusBarHeightPixels();
      mTextViewStatus.setHeight(statusBarHeight);

      StatusManager statusManager = getAppState().statusManager();
      statusManager.addObserver(this);

      // Update what we're (not) displaying to reflect current status.
      update(statusManager, statusManager.getCurrentStatus());
    }
  }

  @Override
  protected void onPause() {
    super.onPause();

    // Don't subscribe to status manager updates if activity is not active.
    if (mTextViewStatus != null) {
      getAppState().statusManager().deleteObserver(this);
    }
  }

  protected void showSoftInput() {
    InputMethodManager imm = (InputMethodManager)getSystemService(Context.INPUT_METHOD_SERVICE);
    View view = getCurrentFocus() != null ? getCurrentFocus() : findViewById(android.R.id.content);
    imm.showSoftInput(view, InputMethodManager.SHOW_IMPLICIT);
  }

  protected void hideSoftInput() {
    InputMethodManager imm = (InputMethodManager)getSystemService(Context.INPUT_METHOD_SERVICE);
    View view = getCurrentFocus() != null ? getCurrentFocus() : findViewById(android.R.id.content);
    imm.hideSoftInputFromWindow(view.getWindowToken(), 0);
  }

  /**
   * Handle updates for Observables that we've registered with.
   * For now, this handles status message updates, but may handle other types of updates in the future.
   */
  @Override
  public void update(Observable observable, Object data) {
    if (getAppState().statusManager() == observable) {
      // Note: There are some problems that we may need or want to fix/address:
      // 1) When we hide the Android status bar, the user will not be able to pull down to get to their notifications.
      // 2) If Viewfinder is running, and the user does pull down to get to their notifications, the next time that
      //    Viewfinder sets the status (and hides the Android Status), the Viewfinder app will be brought to the front.
      //    This is very unfriendly behaviour.
      // TODO(mike): investigate ways to mitigate these issues.
      mTextViewStatus.setText((String)data);

      if (null == data) {
        // Show Android status bar (hides ours).
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN);
      } else {
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN);
      }
    }
  }
}
