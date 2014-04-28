// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.app.Activity;
import android.os.Bundle;
import android.support.v4.view.ViewPager;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

/**
 * Hosts a ViewPager where each page represents a conversation.
 */
public class ConvFragment extends BaseFragment {
  private static final String TAG = "Viewfinder.ConvFragment";
  private static final String ARG_INITIAL_POSITION = "co.viewfinder.InitialPosition";
  private int mPositionMostVisible = -1;

  private OnConvFragmentListener mCallback = null;

  public interface OnConvFragmentListener {
    public void onClose();
  }

  @Override
  public void onAttach(Activity activity) {
    super.onAttach(activity);
    mCallback = (OnConvFragmentListener) activity;
  }

  public static ConvFragment newInstance(int initialPosition) {
    ConvFragment convFragment = new ConvFragment();
    Bundle args = new Bundle();
    args.putInt(ARG_INITIAL_POSITION, initialPosition);
    convFragment.setArguments(args);
    return convFragment;
  }

  @Override
  public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
    View view = inflater.inflate(R.layout.conv_fragment, container, false);

    int initialPosition = getArguments().getInt(ARG_INITIAL_POSITION);

    final TextView pageHeaderTitleTextView = (TextView)view.findViewById(R.id.convFragment_titleBarTextView);
    pageHeaderTitleTextView.setText(R.string.convPage_headerTitle);

    final ConvPagerAdapter convPagerAdapter = new ConvPagerAdapter(getChildFragmentManager(),
                                                             getViewData().getInboxViewData());
    ViewPager viewPager = (ViewPager)view.findViewById(R.id.convFragment_viewpager);
    viewPager.setAdapter(convPagerAdapter);
    viewPager.setCurrentItem(initialPosition);
    viewPager.setOnPageChangeListener(new ViewPager.SimpleOnPageChangeListener() {
      @Override
      public void onPageScrolled(int i, float v, int i2) {
        int positionMostVisible = Math.round(i + v);
        if (positionMostVisible != mPositionMostVisible) {
          ViewData.ConvSummaryViewData.ConvSummaryItemViewData convSummaryItemViewData =
              getViewData().getInboxViewData().getItem(positionMostVisible);
          pageHeaderTitleTextView.setText(convSummaryItemViewData.getTitle());
          mPositionMostVisible = positionMostVisible;
        }
      }
    });

    view.findViewById(R.id.convFragment_titleBarBackButton).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onClose();
      }
    });

    return view;
  }
}
