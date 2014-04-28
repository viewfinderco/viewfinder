// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.support.v4.app.Fragment;
import android.support.v4.app.FragmentStatePagerAdapter;
import android.view.View;

/**
 * This creates SinglePhotoFragment's as requested from the ViewPager hosted by SinglePhotoPagerFragment.
 */
public class SinglePhotoAdapter extends FragmentStatePagerAdapter {
  private final static String TAG = "Viewfinder.SinglePhotoAdapter";

  private int mHeaderVisibility = View.VISIBLE;
  private long mConvViewId;
  private ViewData.PhotoViewData mPhotoViewData;

  public SinglePhotoAdapter(android.support.v4.app.FragmentManager fm,
                            long convViewId,
                            ViewData.PhotoViewData photoViewData) {
    super(fm);
    mConvViewId = convViewId;
    mPhotoViewData = photoViewData;
  }

  @Override
  public Fragment getItem(int i) {
    // Materialize a single photo page fragment for the requested photo.
    SinglePhotoFragment singlePhotoFragment = SinglePhotoFragment.newInstance(mConvViewId, i, mHeaderVisibility);
    return singlePhotoFragment;
  }

  @Override
  public int getCount() {
    return mPhotoViewData.getCount();
  }

  @Override
  public int getItemPosition(Object object) {
    // Trick to force ViewPager to re-request all SinglePhotoFragment's from this adapter after it gets a
    //   data change notification.
    return POSITION_NONE;
  }

  public void setHeaderVisibility(int visibility) {
    mHeaderVisibility = visibility;
    // TODO(mike): Consider keeping track of any active SinglePhotoFragments and explicitly updating just them
    //  in this case, instead of forcing recreation of all of them.
    notifyDataSetChanged();
  }
}
