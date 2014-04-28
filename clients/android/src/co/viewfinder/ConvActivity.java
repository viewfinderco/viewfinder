// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.content.Intent;
import android.os.Bundle;
import android.support.v4.app.Fragment;
import android.support.v4.app.FragmentManager;
import android.util.Log;

/**
 * This manages the UI relating to conversations.
 * It is launched when a conversation is selected from a conversation summary view such as the inbox view.
 */
public class ConvActivity extends BaseActivity implements
    ConvPageFragment.OnConvPageListener,
    ConvFragment.OnConvFragmentListener {
  private static final String TAG = "viewfinder.ConvActivity";
  private static final String TAG_CONV_FRAGMENT = "co.viewfinder.ConvFragment";

  public static final String EXTRA_PAGE_POSITION = "co.viewfinder.InboxPosition";

  @Override
  public void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    setContentView(R.layout.statusbar_activity);

    FragmentManager fm = getSupportFragmentManager();
    Fragment fragment = fm.findFragmentByTag(TAG_CONV_FRAGMENT);
    if (fragment == null) {
      fragment = ConvFragment.newInstance(getIntent().getIntExtra(EXTRA_PAGE_POSITION, -1));
      fm.beginTransaction()
          .add(R.id.statusbar_content, fragment, TAG_CONV_FRAGMENT)
          .commit();
    }
  }

  public void onClose() {
    super.onBackPressed();
  }

  /**
   * Click of photo from a conversation item.
   */
  public void onClickPhoto(long convViewId, long photoViewId) {
    Intent i = new Intent(ConvActivity.this, SinglePhotoActivity.class);
    i.putExtra(SinglePhotoActivity.EXTRA_CONV_VIEW_ID, convViewId);
    i.putExtra(SinglePhotoActivity.EXTRA_PHOTO_VIEW_ID, photoViewId);
    startActivity(i);
  }
}
