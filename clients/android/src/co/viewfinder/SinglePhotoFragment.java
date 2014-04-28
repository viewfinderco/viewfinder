// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import co.viewfinder.Time;

import android.app.Activity;
import android.graphics.Bitmap;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.RelativeLayout;
import android.widget.TextView;

import uk.co.senab.photoview.PhotoView;
import uk.co.senab.photoview.PhotoViewAttacher;

import java.util.Date;

/**
 * This is the fragment which holds the "single photo" image.
 * It is the paging element of the ViewPager in SinglePhotoPagerFragment.
 * It is created by the SinglePhotoAdapter as the SinglePhotoPagerFragment's ViewPager gets items from it.
 */
public class SinglePhotoFragment extends BaseFragment {
  private final static String TAG = "Viewfinder.SinglePhotoFragment";
  private final static String ARG_CONV_VIEW_DATA_ID = "co.viewfinder.conv_view_data_id";
  private final static String ARG_PHOTO_POSITION = "co.viewfinder.photo_position";
  private final static String ARG_HEADER_VISIBILITY = "co.viewfinder.header_visibility";

  private OnSinglePhotoListener mCallback;

  public interface OnSinglePhotoListener {
    public void onToggleHeaderFooter();
  }

  public static SinglePhotoFragment newInstance(long convViewDataId, int photoPosition, int headerVisibility) {
    SinglePhotoFragment singlePhotoFragment = new SinglePhotoFragment();
    Bundle args = new Bundle();
    args.putLong(ARG_CONV_VIEW_DATA_ID, convViewDataId);
    args.putInt(ARG_PHOTO_POSITION, photoPosition);
    args.putInt(ARG_HEADER_VISIBILITY, headerVisibility);
    singlePhotoFragment.setArguments(args);
    return singlePhotoFragment;
  }

  @Override
  public void onAttach(Activity activity) {
    super.onAttach(activity);
    mCallback = (OnSinglePhotoListener)getActivity();
  }

  @Override
  public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
    long convViewDataId = getArguments().getLong(ARG_CONV_VIEW_DATA_ID);
    int photoPosition = getArguments().getInt(ARG_PHOTO_POSITION);
    int headerVisibility = getArguments().getInt(ARG_HEADER_VISIBILITY);

    View view = inflater.inflate(R.layout.single_photo_page, container, false);

    ViewData.PhotoViewData.PhotoItemViewData photoItem =
        getViewData().getConvViewDataFromId(convViewDataId).getAllPhotos().getItem(photoPosition);

    PhotoView imageViewSinglePhoto = (PhotoView)view.findViewById(R.id.imageView_singlePhoto);
    imageViewSinglePhoto.setScaleType(ImageView.ScaleType.FIT_CENTER);
    Bitmap bitmap = getAppState().bitmapFetcher().fetch(getDisplayWidth(),
                                                        getDisplayHeight(),
                                                        BitmapFetcher.DIMENSIONS_AT_MOST,
                                                        photoItem);
    imageViewSinglePhoto.setImageBitmap(bitmap);

    TextView textViewTimeDate = (TextView)view.findViewById(R.id.textView_timeDate);
    textViewTimeDate.setText(Time.formatExactTime(photoItem.getTimestamp()));

    TextView textViewLocation = (TextView)view.findViewById(R.id.textView_location);
    textViewLocation.setText(photoItem.getLocation());

    RelativeLayout header = (RelativeLayout)view.findViewById(R.id.relativeLayout_singlePhotoPageHeader);
    header.setVisibility(headerVisibility);

    imageViewSinglePhoto.setOnViewTapListener(new PhotoViewAttacher.OnViewTapListener() {
      @Override
      public void onViewTap(View v, float x, float y) {
        mCallback.onToggleHeaderFooter();
      }
    });

    return view;
  }
}
