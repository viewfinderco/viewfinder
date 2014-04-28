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
 * UI for photo access.
 */
public class MyPhotosFragment extends BaseFragment {
  private static final String TAG = "viewfinder.MyPhotosFragment";

  private OnMyPhotosListener mCallback = null;

  public interface OnMyPhotosListener {
  }

  @Override
  public void onAttach(Activity activity) {
    super.onAttach(activity);
    mCallback = (OnMyPhotosListener) activity;
  }

  @Override
  public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
    Log.d(TAG, "onCreateView()");
    View view = inflater.inflate(R.layout.fragment_my_photos, container, false);

    return view;
  }

}
