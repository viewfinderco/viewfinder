// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.os.Bundle;
import android.support.v4.app.Fragment;
import android.support.v4.app.FragmentManager;
import android.util.Log;

/**
 * Manage creation of a new conversation.
 */
public class ComposeActivity extends BaseActivity  implements ComposeFragment.OnComposeListener {
  private final static String TAG = "Viewfinder.ComposeActivity";
  private static final String TAG_COMPOSE_FRAGMENT = "co.viewfinder.compose_fragment";

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    Log.d(TAG, "OnCreate()");
    super.onCreate(savedInstanceState);
    setContentView(R.layout.statusbar_activity);

    FragmentManager fm = getSupportFragmentManager();
    Fragment fragment = fm.findFragmentByTag(TAG_COMPOSE_FRAGMENT);
    if (fragment == null) {
      fragment = new ComposeFragment();
      fm.beginTransaction()
          .add(R.id.statusbar_content, fragment, TAG_COMPOSE_FRAGMENT)
          .commit();
    }
  }
}
