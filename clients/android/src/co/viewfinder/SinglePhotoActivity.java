// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.os.Bundle;
import android.support.v4.app.Fragment;
import android.support.v4.app.FragmentManager;
import android.util.Log;
import android.view.View;

/**
 *
 */
public class SinglePhotoActivity extends BaseActivity implements SinglePhotoFragment.OnSinglePhotoListener {
  private static final String TAG = "viewfinder.SinglePhotoActivity";
  private static final String TAG_SINGLE_PHOTO_PAGER_FRAGMENT = "co.viewfinder.single_photo_pager_fragment";
  private static final String TAG_SINGLE_PHOTO_HEADER_FOOTER_VISIBILITY =
      "co.viewfinder.single_photo_header_footer_visibility";

  public static final String EXTRA_CONV_VIEW_ID = "co.viewfinder.conv_view_id";
  public static final String EXTRA_PHOTO_VIEW_ID = "co.viewfinder.photo_view_id";

  private int mSinglePhotoHeaderFooterVisibility = View.VISIBLE;

  public int getCurrentHeaderFooterVisibility() { return mSinglePhotoHeaderFooterVisibility;}

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    setContentView(R.layout.activity_single_photo);

    if (null != savedInstanceState) {
      mSinglePhotoHeaderFooterVisibility = savedInstanceState.getInt(TAG_SINGLE_PHOTO_HEADER_FOOTER_VISIBILITY);
    }

    FragmentManager fm = getSupportFragmentManager();
    Fragment fragment = fm.findFragmentByTag(TAG_SINGLE_PHOTO_PAGER_FRAGMENT);
    if (null == fragment) {
      long convViewId = getIntent().getLongExtra(EXTRA_CONV_VIEW_ID, 0);
      long photoViewId = getIntent().getLongExtra(EXTRA_PHOTO_VIEW_ID, 0);
      fragment = SinglePhotoPagerFragment.newInstance(convViewId, photoViewId);
      fm.beginTransaction()
          .add(R.id.layout_singlePhotoActivity, fragment, TAG_SINGLE_PHOTO_PAGER_FRAGMENT)
          .commit();
    }

    // We always want the status bar hidden in single photo view.
    maybeDimAndroidNavigationButtons();
  }

  /**
   * Click of photo in single photo view.
   * This is used to toggle the visibility of the header and footer information in single photo view.
   */
  public void onToggleHeaderFooter() {
    Log.d(TAG, "onToggleHeaderFooter: ");

    // Toggle visibility of single photo header/footer.
    mSinglePhotoHeaderFooterVisibility = View.VISIBLE == mSinglePhotoHeaderFooterVisibility ?
        View.INVISIBLE :
        View.VISIBLE;

    SinglePhotoPagerFragment singlePhotoPagerFragment =
        (SinglePhotoPagerFragment)getSupportFragmentManager().findFragmentByTag(TAG_SINGLE_PHOTO_PAGER_FRAGMENT);
    if (null != singlePhotoPagerFragment) {
      singlePhotoPagerFragment.onSetHeaderFooterVisibility(mSinglePhotoHeaderFooterVisibility);
      maybeDimAndroidNavigationButtons();
    }
  }

  private void maybeDimAndroidNavigationButtons() {
    if (View.INVISIBLE == mSinglePhotoHeaderFooterVisibility) {
      if (Utils.isHoneycombCapableDevice()) {
        // Dim the android navigation buttons.
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LOW_PROFILE);
      }
    }
  }

  @Override
  protected void onSaveInstanceState(Bundle outState) {
    super.onSaveInstanceState(outState);
    outState.putInt(TAG_SINGLE_PHOTO_HEADER_FOOTER_VISIBILITY, mSinglePhotoHeaderFooterVisibility);
  }
}
