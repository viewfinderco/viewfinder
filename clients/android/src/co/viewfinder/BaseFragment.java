// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.app.Activity;
import android.content.Context;
import android.support.v4.app.Fragment;
import android.view.inputmethod.InputMethodManager;

/**
 * Contains code common to most or all Fragments.
 */
public class BaseFragment extends Fragment {
  private static final String TAG = "Viewfinder.BaseFragment";
  private BaseActivity mBaseActivity = null;

  protected BaseActivity getBaseActivity() { return mBaseActivity; }
  protected AppState getAppState() { return (AppState)getActivity().getApplication(); }
  protected ViewData getViewData() { return ((AppState)getActivity().getApplication()).getViewData(); }

  /**
   * Get the width of the display in pixels.
   * Note: In general, this is NOT good practice, but will be sufficient until we support
   *   fragments side by side on tablet devices.
   */
  public int getDisplayWidth() { return getAppState().getDisplayWidthPixels(); }

  /**
   * Get the height of the display in pixels.
   * Note: In general, this is NOT good practice, but will be sufficient until we support
   *   fragments side by side on tablet devices.
   */
  public int getDisplayHeight() {
    return getAppState().getDisplayHeightPixels();
  }

  @Override
  public void onAttach(Activity activity) {
    super.onAttach(activity);
    mBaseActivity = (BaseActivity)activity;
  }

  protected void showSoftInput() {
    InputMethodManager imm = (InputMethodManager) getActivity().getSystemService(Context.INPUT_METHOD_SERVICE);
    imm.showSoftInput(getActivity().getCurrentFocus(), InputMethodManager.SHOW_IMPLICIT);
  }

  protected void hideSoftInput() {
    InputMethodManager imm = (InputMethodManager) getActivity().getSystemService(Context.INPUT_METHOD_SERVICE);
    imm.hideSoftInputFromWindow(getView().getWindowToken(), 0);
  }

  protected ErrorDialogManager getErrorDialogManager() {
    return mBaseActivity.getErrorDialogManager();
  }
}
