// Copyright 2013 Viewfinder. All rights reserved.
// Author: Andy Kimball
package co.viewfinder;

import android.os.Bundle;
import android.util.Log;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.RelativeLayout;

/**
 * Handle main welcome view that is always visible during initial auth.
 */
public class AuthFragment extends BaseFragment {
  private View mView;

  private static final String TAG = "Viewfinder.AuthFragment";

  @Override
  public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
    Log.d(TAG, "onCreateView");

    mView = (RelativeLayout)inflater.inflate(R.layout.auth_fragment, container, false);
    return mView;
  }
}
