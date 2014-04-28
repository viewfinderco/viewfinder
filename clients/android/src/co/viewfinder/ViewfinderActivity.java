// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Bitmap;
import android.os.Bundle;
import android.provider.MediaStore;
import android.support.v4.app.Fragment;
import android.support.v4.app.FragmentManager;
import android.util.Log;
import android.view.View;

/**
 * Manage Inbox views as well as launching into Contacts, Profile, and My Photos.
 */
public class ViewfinderActivity extends BaseActivity implements InboxFragment.OnInboxListener {
  private static final String TAG = "viewfinder.ViewfinderActivity";
  private static final String TAG_INBOX_FRAGMENT = "co.viewfinder.InboxFragment";
  private static final int CAMERA_PIC_REQUEST = 0;
  private static final int GALLERY_PIC_REQUEST = 1;

  @Override
  public void onCreate(Bundle savedInstanceState) {
    Log.d(TAG, "onCreate");
    super.onCreate(savedInstanceState);
    setContentView(R.layout.statusbar_activity);

    FragmentManager fm = getSupportFragmentManager();
    Fragment fragment = fm.findFragmentByTag(TAG_INBOX_FRAGMENT);
    if (null == fragment) {
      fragment = new InboxFragment();
      fm.beginTransaction()
          .add(R.id.statusbar_content, fragment, TAG_INBOX_FRAGMENT)
          .commit();
    }
  }

  @Override
  public void onInboxItem(int position) {
    Log.d(TAG, "onInboxItem: " + position);
    Intent i = new Intent(ViewfinderActivity.this, ConvActivity.class);
    i.putExtra(ConvActivity.EXTRA_PAGE_POSITION, position);
    startActivity(i);
  }

  @Override
  public void onProfile() {
    Log.d(TAG, "onProfile");

    Intent i = new Intent(ViewfinderActivity.this, ProfileActivity.class);
    startActivity(i);
    overridePendingTransition(new TitleBarActivityTransition(this));
  }

  @Override
  public void onContacts() {
    Log.d(TAG, "onContacts");

    Intent i = new Intent(ViewfinderActivity.this, ContactsActivity.class);
    startActivity(i);
  }

  @Override
  public void onMyPhotos() {
    Log.d(TAG, "onMyPhotos");

    // This let's one pick a single photo.
    // Phone manufacturers frequently ship their own gallery apps and may remove the stock Android gallery app
    //   from what they ship.  So at the very least, we'll need to do our own simple gallery/photo picker that
    //   supports multi-select, etc...  For now an empty activity, MyPhotosActivity, exists which will do that.
    //   It can be launched from the profile page photos count.
    Intent i = new Intent(Intent.ACTION_PICK);
    i.setType("image/*");
    if (Utils.isHoneycombCapableDevice()) {
      i.putExtra(Intent.EXTRA_LOCAL_ONLY, true);
    }
    startActivityForResult(i, GALLERY_PIC_REQUEST);
  }

  @Override
  public void onCompose() {
    Log.d(TAG, "onCompose");

    Intent i = new Intent(ViewfinderActivity.this, ComposeActivity.class);
    startActivity(i);
  }

  @Override
  public void onEditInbox() {
    Log.d(TAG, "onEditInbox");
  }

  @Override
  public void onCamera() {
    Log.d(TAG, "onCamera");

    // TODO(mike): consider any options we want to launch this with.
    Intent i = new Intent(MediaStore.INTENT_ACTION_STILL_IMAGE_CAMERA);
    startActivityForResult(i, CAMERA_PIC_REQUEST);
  }

  @Override
  protected void onActivityResult(int requestCode, int resultCode, Intent data) {
    Log.d(TAG, "onActivityResult");
    super.onActivityResult(requestCode, resultCode, data);
    if (CAMERA_PIC_REQUEST == requestCode) {
      Log.d(TAG, "onActivityResult(CAMERA_PIC_REQUEST, " + resultCode + ")");
      if (Activity.RESULT_OK == resultCode) {
        Bitmap thumbnail = (Bitmap) data.getExtras().get("data");
        // TODO(mike):  Add this image to photo manager.
        Log.d(TAG, "onActivityResult: Got bitmap: " + thumbnail);
      } else if (Activity.RESULT_CANCELED == resultCode) {
        Log.d(TAG, "onActivityResult: image capture canceled.");
      }
    } else if (GALLERY_PIC_REQUEST == requestCode) {
      Log.d(TAG, "onActivityResult(GALLERY_PIC_REQUEST, " + resultCode + ")");
      if (Activity.RESULT_OK == resultCode) {
        Log.d(TAG, "onActivityResult: " + data.getData());
      }
      else if (Activity.RESULT_CANCELED == resultCode) {
        Log.d(TAG, "onActivityResult: photo pick canceled.");
      }
    }
  }
}
