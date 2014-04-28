// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.support.v4.app.Fragment;
import android.support.v4.app.FragmentManager;
import android.support.v4.app.FragmentTransaction;
import android.util.Log;
import android.view.View;
import android.view.animation.AlphaAnimation;

/**
 * Activity to manage the user's profile.
 */
public class ProfileActivity extends BaseActivity implements ProfileFragment.OnProfileListener {
  private static final String TAG = "viewfinder.ProfileActivity";
  private static final String TAG_PROFILE = "co.viewfinder.ProfileFragment";

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);

    setContentView(R.layout.statusbar_activity);

    FragmentTransaction ft = getSupportFragmentManager().beginTransaction();
    ft.add(R.id.statusbar_content, new ProfileFragment(), TAG_PROFILE);
    ft.commit();
  }

  @Override
  public void onMyInfo() {
    Intent i = new Intent(ProfileActivity.this, MyInfoActivity.class);
    startActivity(i);
    overridePendingTransition(new TitleBarActivityTransition(this));
  }

  @Override
  public void onSettings() {
    Intent i = new Intent(ProfileActivity.this, SettingsActivity.class);
    startActivity(i);
    overridePendingTransition(new TitleBarActivityTransition(this));
  }

  @Override
  public void onContacts() {
    Intent i = new Intent(ProfileActivity.this, ContactsActivity.class);
    startActivity(i);
  }

  @Override
  public void onMyPhotos() {
    Intent i = new Intent(ProfileActivity.this, MyPhotosActivity.class);
    startActivity(i);
  }

  @Override
  public void onInbox() {
    Intent i = new Intent(ProfileActivity.this, ViewfinderActivity.class);
    startActivity(i);
  }
}
