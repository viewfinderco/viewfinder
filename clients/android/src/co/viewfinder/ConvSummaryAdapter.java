// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.content.Context;
import android.database.DataSetObserver;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.*;

/**
 * UI component that materializes conversation summary item fragments.
 * It feeds the ListView hosted in InboxFragment.
 */
public class ConvSummaryAdapter extends BaseAdapter {
  private static final String TAG = "Viewfinder.ConvSummaryAdapter";
  private static final String PHOTO_SYMBOL = "\u2632";
  private static final String USER_SYMBOL = "\u2633";
  private static final String COMMENT_SYMBOL = "\u2634";

  // The following are subject to change depending on how responsive we want to be to the screen size.
  private static final int CONV_SUMMARY_THUMBNAIL_SIZE = 120;
  private static final int MAX_THUMNAIL_COUNT = 4;

  private InboxFragment mInboxFragment = null;
  private LayoutInflater mInflater = null;
  private ViewData.ConvSummaryViewData mConvSummaryViewData = null;
  private int mConvSummaryCardPaddingPixels;

  /**
   * Cache view.FindById() calls.
   */
  static class ViewHolder {
    public TextView title;
    public TextView participantCount;
    public TextView participants;
    public TextView imageCount;
    public TextView commentCount;
    public TextView lastUpdate;
    public PhotoImageView[] itemPhotos;
    public LinearLayout itemPhotosContainer;
  }

  public ConvSummaryAdapter(InboxFragment inboxFragment) {
    mInboxFragment = inboxFragment;
    mInflater = (LayoutInflater) mInboxFragment.getActivity().getSystemService(Context.LAYOUT_INFLATER_SERVICE);
    mConvSummaryCardPaddingPixels =
        mInboxFragment.getResources().getDimensionPixelSize(R.dimen.convSummary_cardPadding);
  }

  public void setInboxItems(ViewData.ConvSummaryViewData convSummaryViewData) {
    mConvSummaryViewData = convSummaryViewData;
    mConvSummaryViewData.registerDataSetObserver(new DataSetChangeHandler());
  }

  @Override
  public int getCount() { return mConvSummaryViewData.getCount(); }
  @Override
  public Object getItem(int position) { return mConvSummaryViewData.getItem(position); }
  @Override
  public long getItemId(int position) { return mConvSummaryViewData.getItem(position).getId(); }

  public void setListView(ListView listView) {
    listView.setRecyclerListener(new AbsListView.RecyclerListener() {
      @Override
      public void onMovedToScrapHeap(View view) {
        ViewHolder viewHolder = (ViewHolder)view.getTag();
        for (int iPhoto = 0; iPhoto < viewHolder.itemPhotos.length; iPhoto++) {
          // Cancel any fetches for these images given that the containing view is being recycled.
          viewHolder.itemPhotos[iPhoto].cancelFetchRequest();
        }
      }
    });
  }

  @Override
  public View getView(int position, View convertView, ViewGroup parent) {
    if (null == convertView) {
      convertView = mInflater.inflate(R.layout.inbox_item, parent, false);
      ViewHolder viewHolder = new ViewHolder();
      viewHolder.title = (TextView)convertView.findViewById(R.id.textView_title);
      viewHolder.participantCount = (TextView)convertView.findViewById(R.id.textView_participantCount);
      viewHolder.participants = (TextView)convertView.findViewById(R.id.textView_participants);
      viewHolder.imageCount = (TextView)convertView.findViewById(R.id.textView_imageCount);
      viewHolder.commentCount = (TextView)convertView.findViewById(R.id.textView_commentCount);
      viewHolder.lastUpdate = (TextView)convertView.findViewById(R.id.textView_lastUpdate);
      viewHolder.itemPhotosContainer = (LinearLayout)convertView.findViewById(R.id.linearLayout_itemPhotos);
      viewHolder.itemPhotos = new PhotoImageView[mInboxFragment.getViewData().getMaxConvSummaryPhotos()];
      viewHolder.itemPhotos[0] = (PhotoImageView)convertView.findViewById(R.id.imageView_itemPhoto0);
      viewHolder.itemPhotos[1] = (PhotoImageView)convertView.findViewById(R.id.imageView_itemPhoto1);
      viewHolder.itemPhotos[2] = (PhotoImageView)convertView.findViewById(R.id.imageView_itemPhoto2);
      viewHolder.itemPhotos[3] = (PhotoImageView)convertView.findViewById(R.id.imageView_itemPhoto3);
      convertView.setTag(viewHolder);
    }

    return updateView(convertView, mConvSummaryViewData.getItem(position));
  }

  private View updateView(View view, ViewData.ConvSummaryViewData.ConvSummaryItemViewData inboxItem) {
    ViewHolder viewHolder = (ViewHolder)view.getTag();

    viewHolder.title.setText(inboxItem.getTitle());
    viewHolder.participantCount.setText(USER_SYMBOL + " " + inboxItem.getFollowers().length);
    viewHolder.imageCount.setText(PHOTO_SYMBOL + " " + inboxItem.getPhotoCount());
    viewHolder.commentCount.setText(COMMENT_SYMBOL + " " + inboxItem.getCommentCount());
    viewHolder.lastUpdate.setText(Time.formatRelativeTime(inboxItem.getLastUpdateTime(),
                                                          System.currentTimeMillis(),
                                                          Time.TimeFormat.TIME_FORMAT_SHORT));
    viewHolder.participants.setText(Utils.enumeratedStringFromStrings(inboxItem.getFollowers(),
                                                                      false /* skipLast */));

    ViewData.PhotoViewData photoViewData = inboxItem.getConvSummaryItemPhotos();

    // TODO(mike): Much todo for photo layout here. (responsive sizing, paralax, etc..)
    ViewGroup.LayoutParams lp = viewHolder.itemPhotosContainer.getLayoutParams();
    if (photoViewData.getCount() > 0) {
      viewHolder.itemPhotosContainer.setBackgroundColor(
          mInboxFragment.getResources().getColor(android.R.color.transparent));
      // TODO(mike): figure out the best way to present our thumbnails in conv summary view so that they
      //    don't look so bad on Android.  Currently they're getting stretched to fill the screen and
      //    don't look good.  Possible solution is a different layout (maybe 5 or 6 of the last images instead of 4).
      lp.height = Math.round((mInboxFragment.getDisplayWidth() - 2 * mConvSummaryCardPaddingPixels) /
                             (float)MAX_THUMNAIL_COUNT);
    } else {
      // No photos, so switch to a narrow line for separation.
      lp.height = 1;
      viewHolder.itemPhotosContainer.setBackgroundColor(
          mInboxFragment.getResources().getColor(R.color.convSummary_divider));
    }
    viewHolder.itemPhotosContainer.setLayoutParams(lp);

    for (int iPhoto = 0; iPhoto < viewHolder.itemPhotos.length; iPhoto++) {
      viewHolder.itemPhotos[iPhoto].assertNoPendingFetch();
      int visibility = View.GONE;
      if (iPhoto < photoViewData.getCount()) {
        // Fetch the bitmaps.
        viewHolder.itemPhotos[iPhoto].fetchBitmap(
            Math.round((CONV_SUMMARY_THUMBNAIL_SIZE * MAX_THUMNAIL_COUNT) / (float)photoViewData.getCount()),
            CONV_SUMMARY_THUMBNAIL_SIZE,
            BitmapFetcher.DIMENSIONS_AT_LEAST,
            photoViewData.getItem(iPhoto),
            mInboxFragment.getAppState());
        visibility = View.VISIBLE;
      }
      viewHolder.itemPhotos[iPhoto].setVisibility(visibility);
    }

    return view;
  }

  /**
   * Proxy to be notified of underlying data change in order to pass it onto the attached ListView.
   */
  private class DataSetChangeHandler extends DataSetObserver {
    @Override
    public void onChanged() {
      notifyDataSetChanged();
    }
  }
}
