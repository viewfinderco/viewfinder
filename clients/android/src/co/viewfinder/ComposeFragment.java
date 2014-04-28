// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.app.Activity;
import android.os.Bundle;
import android.util.Log;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;

/**
 *  UI for conversation creation.
 */
public class ComposeFragment extends BaseFragment {
  private static final String TAG = "Viewfinder.ComposeFragment";

  private OnComposeListener mCallback = null;

  public interface OnComposeListener {
  }

  @Override
  public void onAttach(Activity activity) {
    super.onAttach(activity);
    mCallback = (OnComposeListener) activity;
  }

  @Override
  public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
    Log.d(TAG, "onCreateView()");

    View view = inflater.inflate(R.layout.fragment_compose, container, false);

    return view;
  }

}
