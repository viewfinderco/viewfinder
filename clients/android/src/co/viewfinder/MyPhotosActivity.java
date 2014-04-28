// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.os.Bundle;
import android.support.v4.app.Fragment;
import android.support.v4.app.FragmentManager;
import android.util.Log;

/**
 * Activity to access photos.
 */
public class MyPhotosActivity extends BaseActivity implements MyPhotosFragment.OnMyPhotosListener {
  private static final String TAG = "viewfinder.MyPhotosActivity";
  private static final String TAG_MY_PHOTOS_FRAGMENT = "co.viewfinder.my_photos_fragment";

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    Log.d(TAG, "onCreate()");
    super.onCreate(savedInstanceState);
    setContentView(R.layout.statusbar_activity);

    FragmentManager fm = getSupportFragmentManager();
    Fragment fragment = fm.findFragmentByTag(TAG_MY_PHOTOS_FRAGMENT);
    if (fragment == null) {
      fragment = new MyPhotosFragment();
      fm.beginTransaction()
          .add(R.id.statusbar_content, fragment, TAG_MY_PHOTOS_FRAGMENT)
          .commit();
    }
  }
}
