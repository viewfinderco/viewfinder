// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.support.v4.app.Fragment;
import android.support.v4.app.FragmentStatePagerAdapter;

/**
 *  This creates ConvPageFragment's to feed the ViewPager in ConvFragment.
 */
public class ConvPagerAdapter extends FragmentStatePagerAdapter {
  private static final String TAG = "viewfinder.ConvPagerAdapter";

  private ViewData.ConvSummaryViewData mConvSummaryViewData;

  public ConvPagerAdapter(android.support.v4.app.FragmentManager fm,
                          ViewData.ConvSummaryViewData convSummaryViewData) {
    super(fm);
    mConvSummaryViewData = convSummaryViewData;
  }

  @Override
  public Fragment getItem(int i) {
    // Materialize a conversation page fragment for the requested inbox item.
    return ConvPageFragment.newInstance(mConvSummaryViewData.getItem(i).getId());
  }

  @Override
  public int getCount() {
    return mConvSummaryViewData.getCount();
  }
}
