// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.app.Activity;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewTreeObserver;
import android.widget.AbsListView;
import android.widget.FrameLayout;
import co.viewfinder.widgets.SpringyListView;

/**
 * Represents a conversation where the primary element is a ListView which holds items from the conversation.
 * ConvPageFragment is created by ConvPagerAdapter to feed the ViewPager in ConvFragment.
 */
public class ConvPageFragment extends BaseFragment  {
  private final static String TAG = "Viewfinder.ConvPageFragment";
  private final static String ARG_CONV_SUMMARY_ITEM_VIEW_DATA_ID = "co.viewfinder.ConvSummaryItemViewDataId";

  private OnConvPageListener mCallback = null;
  private int mListViewHeight = 0;

  public interface OnConvPageListener {
    public void onClickPhoto(long convViewId, long photoViewId);
  }

  public static ConvPageFragment newInstance(long convViewDataId)
  {
    ConvPageFragment convPageFragment = new ConvPageFragment();
    Bundle args = new Bundle();
    args.putLong(ARG_CONV_SUMMARY_ITEM_VIEW_DATA_ID, convViewDataId);
    convPageFragment.setArguments(args);
    return convPageFragment;
  }

  @Override
  public void onAttach(Activity activity) {
    super.onAttach(activity);
    mCallback = (OnConvPageListener)activity;
  }

  @Override
  public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
    View view = inflater.inflate(R.layout.conv_page, container, false);

    long convSummaryItemViewDataId = getArguments().getLong(ARG_CONV_SUMMARY_ITEM_VIEW_DATA_ID);
    final ViewData.ConvViewData convViewData = getViewData().getConvViewDataFromSummaryItemId(convSummaryItemViewDataId);

    PhotoImageView photoImageView = (PhotoImageView)view.findViewById(R.id.convPage_backgroundCoverPhoto);

    ConvAdapter convAdapter = new ConvAdapter(this, convViewData);
    final SpringyListView listView = (SpringyListView)view.findViewById(R.id.convPage_listView);

    final ViewData.PhotoViewData coverPhoto = convViewData.getCoverPhoto();
    if (coverPhoto.getCount() > 0) {
      photoImageView.fetchBitmap(getDisplayWidth(),
                                 Math.round(getDisplayHeight() / 2.0f),
                                 BitmapFetcher.DIMENSIONS_AT_LEAST,
                                 coverPhoto.getItem(0),
                                 getAppState());
      final FrameLayout listViewHeaderForCoverPhoto = new FrameLayout(getActivity());
      listViewHeaderForCoverPhoto.setLayoutParams(new AbsListView.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0));
      listView.addHeaderView(listViewHeaderForCoverPhoto);
      listViewHeaderForCoverPhoto.setOnClickListener(new View.OnClickListener() {
        @Override
        public void onClick(View v) {
          onClickPhoto(convViewData.getId(), coverPhoto.getItem(0).getId());
        }
      });
      listView.getViewTreeObserver().addOnGlobalLayoutListener(new ViewTreeObserver.OnGlobalLayoutListener() {
        public void onGlobalLayout() {
          int listViewHeight = listView.getHeight();

          // Only do anything if the height of the ListView changes.
          if (listViewHeight != mListViewHeight) {
            mListViewHeight = listViewHeight;
            listViewHeaderForCoverPhoto.setLayoutParams(
                new AbsListView.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                                             Math.round(mListViewHeight * 0.3f)));
          }
        }
      });
    }

    listView.setAdapter(convAdapter);
    convAdapter.setListView(listView);

    return view;
  }

  /**
   * Click of photo in conversation item (share photo, comment or cover photo).
   */
  public void onClickPhoto(long convViewId, long photoViewId) {
    // Propagate click of photo back to controlling activity.
    mCallback.onClickPhoto(convViewId, photoViewId);
  }
}
