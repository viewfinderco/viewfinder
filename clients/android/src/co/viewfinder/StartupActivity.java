// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;

/**
 * First Activity to run when Viewfinder app is started.
 * This activity will ensure/wait for AppState initialization.
 * Once AppState initialization has completed, we can determine if
 * we need to switch to AuthActivity or to ViewfinderActivity (if already signed in).
 */
public class StartupActivity extends BaseActivity {
  @Override
  public void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    setContentView(R.layout.startup_activity);
  }

  @Override
  protected void onResume() {
    super.onResume();

    // Simulate startup delay to load database, etc..
    new Handler().postDelayed(new Runnable() {
      public void run() {
        long user_id = ((AppState) getApplication()).getUserId();
        Intent i = new Intent(StartupActivity.this, user_id == 0 ? AuthActivity.class : ViewfinderActivity.class);
        startActivity(i);
      }
    }, 500);
  }

  @Override
  protected void onPause() {
    super.onPause();
    overridePendingTransition(0, R.anim.startup);
  }
}
