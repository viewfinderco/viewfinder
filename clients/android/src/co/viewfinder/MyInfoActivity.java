// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.content.Intent;
import android.os.Bundle;
import android.support.v4.app.FragmentManager;
import android.support.v4.app.FragmentTransaction;
import android.util.Log;
import android.view.animation.Animation;
import android.view.animation.AnimationUtils;
import co.viewfinder.proto.ContactMetadataPB;

/**
 * Activity to show 'My Info' from profile.
 */
public class MyInfoActivity extends BaseActivity implements
    MyInfoFragment.OnMyInfoListener,
    MyInfoEditFragment.OnMyInfoEditListener,
    MyInfoPasswordFragment.OnMyInfoPasswordListener {
  private static final String TAG = "Viewfinder.MyInfoActivity";
  private static final String TAG_MYINFO = "co.viewfinder.MyInfoFragment";
  private static final String TAG_MYINFO_EDIT = "co.viewfinder.MyInfoEditFragment";
  private static final String TAG_MYINFO_PASSWORD = "co.viewfinder.MyInfoPasswordFragment";

  private MyInfoFragment mMyInfoFragment;

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);

    setContentView(R.layout.statusbar_activity);

    mMyInfoFragment = new MyInfoFragment();

    FragmentTransaction ft = getSupportFragmentManager().beginTransaction();
    ft.add(R.id.statusbar_content, mMyInfoFragment, TAG_MYINFO);
    ft.commit();
  }

  /**
   *
   * ---------- OnMyInfoListener callbacks ----------
   *
   */

  @Override
  public void onEditName() {
    FragmentManager fm = getSupportFragmentManager();
    FragmentTransaction ft = fm.beginTransaction();

    ft.setCustomAnimations(R.anim.fade_in, 0, 0, R.anim.fade_out);
    ft.add(R.id.statusbar_content, new MyInfoEditFragment(), TAG_MYINFO_EDIT);
    ft.addToBackStack(null);

    ft.commit();

    // Darken main fragment while edit fragment is showing.
    mMyInfoFragment.getView().setAnimation(AnimationUtils.loadAnimation(this, R.anim.darken));
  }

  @Override
  public void onChangePassword() {
    FragmentManager fm = getSupportFragmentManager();
    FragmentTransaction ft = fm.beginTransaction();

    ft.setCustomAnimations(R.anim.slide_in_bottom, 0, 0, R.anim.slide_out_bottom);
    ft.add(R.id.statusbar_content, new MyInfoPasswordFragment(), TAG_MYINFO_PASSWORD);
    ft.addToBackStack(null);

    ft.commit();

    // Darken main fragment while change password fragment is showing.
    mMyInfoFragment.getView().setAnimation(AnimationUtils.loadAnimation(this, R.anim.darken));
  }

  /**
   *
   * ---------- OnMyInfoEditListener callbacks ----------
   *
   */

  @Override
  public void onEditDone(String firstName, String lastName) {
    // Send the updated name to the server if it was changed.
    ContactMetadataPB.ContactMetadata myself = getAppState().getSelfContact();
    String newName = firstName + " " + lastName;
    if (!newName.equals(myself.getName())) {
      getAppState().contactManager().setMyName(firstName, lastName, newName);
      mMyInfoFragment.onUpdateSelf();
    }

    // Exit edit mode.
    onBackPressed();
  }

  /**
   *
   * ---------- OnMyInfoPasswordListener callbacks ----------
   *
   */

  @Override
  public void onSubmitPasswordChange(String oldPassword, String newPassword) {
    Log.d(TAG, "[onSubmitPasswordChange]");

    getAppState().networkManager().sendChangePassword(
        oldPassword,
        newPassword,
        new NetworkManager.AuthResponseCallback() {
          @Override
          public void run() {
            if (mStatusCode == 200) {
              // Success, so go back to MyInfo screen.
              onBackPressed();
            } else {
              // Show error.
              getErrorDialogManager().show(R.string.error_server, mErrorMsg);
            }
          }
        });
  }

  @Override
  public void onCancelPasswordChange() {
    // Go back to MyInfo screen.
    onBackPressed();
  }

  @Override
  public void onBackPressed() {
    // Lighten main fragment if edit or change password fragment was showing.
    if (getSupportFragmentManager().getBackStackEntryCount() > 0) {
      Animation animation = AnimationUtils.loadAnimation(this, R.anim.lighten);
      animation.setAnimationListener(new Animation.AnimationListener() {
        @Override
        public void onAnimationStart(Animation animation) {
        }

        @Override
        public void onAnimationEnd(Animation animation) {
          // Wait until animation is over to hide keyboard; it looks better.
          hideSoftInput();
        }

        @Override
        public void onAnimationRepeat(Animation animation) {
        }
      });
      mMyInfoFragment.getView().startAnimation(animation);
    }

    super.onBackPressed();
  }
}
