// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.os.Bundle;
import android.support.v4.view.ViewPager;
import android.util.Log;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageButton;
import android.widget.RelativeLayout;

/**
 * This holds the ViewPager that pages through the "single photos".
 * The ViewPager pages through SinglePhotoFragment's.
 * SinglePhotoAdapter creates the SinglePhotoFragment's that feed this ViewPager.
 */
public class SinglePhotoPagerFragment extends BaseFragment {
  private static final String TAG = "Viewfinder.SinglePhotoPagerFragment";
  private static final String ARG_CONV_VIEW_ID = "co.viewfinder.conv_view_id";
  private static final String ARG_PHOTO_VIEW_ID = "co.viewfinder.photo_view_id";

  private RelativeLayout mButtons;
  private SinglePhotoAdapter mSinglePhotoAdapter;

  public static SinglePhotoPagerFragment newInstance(long convViewId, long photoViewId) {
    SinglePhotoPagerFragment singlePhotoPagerFragment = new SinglePhotoPagerFragment();
    Bundle args = new Bundle();
    args.putLong(ARG_CONV_VIEW_ID, convViewId);
    args.putLong(ARG_PHOTO_VIEW_ID, photoViewId);
    singlePhotoPagerFragment.setArguments(args);
    return singlePhotoPagerFragment;
  }

  @Override
  public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
    Log.d(TAG, "onCreateView...  mSinglePhotoAdapter: " + mSinglePhotoAdapter);
    long convViewId = getArguments().getLong(ARG_CONV_VIEW_ID);
    long photoViewId = getArguments().getLong(ARG_PHOTO_VIEW_ID);
    View view = inflater.inflate(R.layout.fragment_single_photo, container, false);

    mButtons = (RelativeLayout)view.findViewById(R.id.single_photo_buttons);


    ViewData.ConvViewData convViewData = getViewData().getConvViewDataFromId(convViewId);
    ViewData.PhotoViewData photoViewData = convViewData.getAllPhotos();

    ViewPager viewPager = (ViewPager)view.findViewById(R.id.viewpager_singlePhoto);

    mSinglePhotoAdapter =
        new SinglePhotoAdapter(getChildFragmentManager(),
                               convViewId,
                               getViewData().getConvViewDataFromId(convViewId).getAllPhotos());
    viewPager.setOffscreenPageLimit(1);
    viewPager.setAdapter(mSinglePhotoAdapter);
    viewPager.setCurrentItem(photoViewData.getItem(photoViewId).getPosition());

    // Buttons
    ImageButton related = (ImageButton)view.findViewById(R.id.button_related);
    related.setOnClickListener(new View.OnClickListener() {
      public void onClick(View v) {
        Log.d(TAG, "Pressed the button");
        return;
      }
    });

    onSetHeaderFooterVisibility(((SinglePhotoActivity)getActivity()).getCurrentHeaderFooterVisibility());

    return view;
  }

  public void onSetHeaderFooterVisibility(int visibility) {
    mButtons.setVisibility(visibility);
    if (null != mSinglePhotoAdapter) {
      mSinglePhotoAdapter.setHeaderVisibility(visibility);
    }
  }
}
