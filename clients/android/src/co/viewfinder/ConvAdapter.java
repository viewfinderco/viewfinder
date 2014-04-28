// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.content.Context;
import android.graphics.Typeface;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.*;
import co.viewfinder.widgets.SpannableBuilder;
import junit.framework.Assert;

import java.util.LinkedList;

/**
 * This adapter produces the views that form the individual parts of a conversation.
 * This is created by ConvPageFragment and feeds the ListView contained within ConvPageFragment.
 */
public class ConvAdapter extends BaseAdapter {
  private static final String TAG = "Viewfinder.ConvAdapter";
  private static final int SHARED_IMAGE_SIZE = 120;
  // In the future, we may consider making this dynamic to respond to different sized screens.
  private static final int SHARED_IMAGES_PER_ROW = 4;

  private ConvPageFragment mConvPageFragment;
  private LayoutInflater mInflater;
  private ViewData.ConvViewData mConvViewData = null;
  private int mSharedImageDesiredSize;
  private int mCommentImageDesiredSize;

  public ConvAdapter(ConvPageFragment convPageFragment, ViewData.ConvViewData convViewData) {
    mConvPageFragment = convPageFragment;
    mConvViewData = convViewData;
    mInflater = (LayoutInflater) mConvPageFragment.getActivity().getSystemService(Context.LAYOUT_INFLATER_SERVICE);
    mCommentImageDesiredSize =
        mConvPageFragment.getResources().getDimensionPixelSize(R.dimen.convItem_commentImage);
    // For now, just assume square images:
    mSharedImageDesiredSize = Math.round(mConvPageFragment.getDisplayWidth() / (float)SHARED_IMAGES_PER_ROW);
  }

  @Override
  public int getCount() { return mConvViewData.getCount(); }
  @Override
  public Object getItem(int position) { return mConvViewData.getItem(position); }
  @Override
  public long getItemId(int position) { return mConvViewData.getItem(position).getId(); }
  @Override
  public int getViewTypeCount() { return ViewData.ConvViewData.ConvItemType.getCount(); }
  @Override
  public int getItemViewType(int position) { return mConvViewData.getItem(position).getItemType().ordinal(); }

  /**
   * Hook into the ListView's recycler so that we can cancel image fetches that obviously no longer matter.
   */
  public void setListView(ListView listView) {
    listView.setRecyclerListener(new AbsListView.RecyclerListener() {
      @Override
      public void onMovedToScrapHeap(View view) {
        ConvViewHolder convViewHolder = (ConvViewHolder)view.getTag();
        convViewHolder.cancelImageViewFetches();
      }
    });
  }

  /**
   * Base ViewHolder that conversation item views can add their ImageView's to so that if they're recycled,
   *   any outstanding image fetches can be canceled.
   */
  class ConvViewHolder {
    public View mViewForBackground;
    public LinkedList<PhotoImageView> mImageViews;

    public ConvViewHolder(View view) {
      mViewForBackground = view.findViewById(R.id.convItem_container);
      view.setTag(this);
    }

    public void setContainerBackground(int resource) {
      mViewForBackground.setBackgroundResource(resource);
    }

    public void addImageView(PhotoImageView photoImageView) {
      if (null == mImageViews) {
        mImageViews = new LinkedList<PhotoImageView>();
      }
      mImageViews.add(photoImageView);
    }
    public void cancelImageViewFetches() {
      if (null != mImageViews) {
        for (PhotoImageView photoImageView : mImageViews) {
          photoImageView.cancelFetchRequest();
        }
      }
    }
  }

  /**
   * Depending on the type of view needed, dispatch to the correct view type getter.
   */
  @Override
  public View getView(int position, View convertView, ViewGroup parent) {
    View view = null;
    ViewData.ConvViewData.ConvItemViewData viewData = mConvViewData.getItem(position);

    switch(viewData.getItemType()) {
      case HEADER:
        view = getHeaderView((ViewData.ConvViewData.ConvHeaderViewData)viewData,
                             convertView,
                             parent);
        break;

      case STARTED:
        view = getFormattedTextView(viewData,
                                    convertView,
                                    parent);
        break;

      case COMMENT:
        view = getCommentView((ViewData.ConvViewData.ConvCommentViewData)viewData,
                              convertView,
                              parent);
        break;

      case SHARE_PHOTOS:
        view = getSharePhotosView((ViewData.ConvViewData.ConvSharePhotosViewData)viewData,
                                  convertView,
                                  parent);
        break;

      case ADD_FOLLOWERS:
        view = getFormattedTextView(viewData,
                                   convertView,
                                   parent);
        break;

      default:
        Assert.fail();
        break;
    }

    Assert.assertNotNull(view);

    setItemBackground(position, view, viewData);

    return view;
  }

  public View getHeaderView(ViewData.ConvViewData.ConvHeaderViewData viewData,
                            View convertView,
                            ViewGroup parent) {
    View view;
    class ViewHolder extends ConvViewHolder {
      public ViewHolder(View view) { super(view); }
      public TextView title;
      public TextView followers;
    }
    ViewHolder viewHolder;

    if (null == convertView) {
      view = mInflater.inflate(R.layout.conv_item_header, parent, false);
      viewHolder = new ViewHolder(view);
      viewHolder.title = (TextView)view.findViewById(R.id.convItem_headerTitle);
      viewHolder.followers = (TextView)view.findViewById(R.id.convItem_headerFollowers);
      viewHolder.followers.setTypeface(null, Typeface.BOLD);
      setContainerMargins(view);
    } else {
      view = convertView;
      viewHolder = (ViewHolder)view.getTag();
    }

    viewHolder.title.setText(viewData.getTitle());
    viewHolder.followers.setText(Utils.enumeratedStringFromStrings(viewData.getFollowers(),
                                                                   false /* skipLast */));
    return view;
  }

  public View getCommentView(ViewData.ConvViewData.ConvCommentViewData viewData,
                             View convertView,
                             ViewGroup parent) {
    final View view;
    class ViewHolder  extends ConvViewHolder {
      public ViewHolder(View view) { super(view); }
      public TextView commenter;
      public TextView commentTimestamp;
      public TextView comment;
      public FrameLayout threading;
      public PhotoImageView commentedImage;
    }
    final ViewHolder viewHolder;

    if (null == convertView) {
      view = mInflater.inflate(R.layout.conv_item_comment, parent, false);
      viewHolder = new ViewHolder(view);
      viewHolder.commenter = (TextView)view.findViewById(R.id.convItem_commenter);
      viewHolder.commentTimestamp = (TextView)view.findViewById(R.id.convItem_commentTimestamp);
      viewHolder.comment = (TextView)view.findViewById(R.id.convItem_comment);
      viewHolder.commentedImage = (PhotoImageView)view.findViewById(R.id.convItem_commentImage);
      viewHolder.threading = (FrameLayout)view.findViewById(R.id.convItem_threading);
      viewHolder.addImageView(viewHolder.commentedImage);
      viewHolder.commenter.setTextColor(mConvPageFragment.getResources().getColor(R.color.conv_text));
      viewHolder.commentTimestamp.setTextColor(mConvPageFragment.getResources().getColor(R.color.conv_textLight));
      viewHolder.comment.setTextColor(mConvPageFragment.getResources().getColor(R.color.conv_text));
      setContainerMargins(view);
    } else {
      view = convertView;
      viewHolder = (ViewHolder)view.getTag();
    }

    viewHolder.commenter.setText(viewData.getCommenter());

    viewHolder.commentTimestamp.setText(Time.formatTime(viewData.getTimestamp()));
    String comment = viewData.getComment();
    String formattedTime = Time.formatTime(viewData.getTimestamp());
    if (viewData.isCombined()) {
      viewHolder.commenter.setVisibility(View.GONE);
      viewHolder.commentTimestamp.setVisibility(View.GONE);
      if (viewData.isTimestampAppended()) {
        viewHolder.comment.setText((new SpannableBuilder(mConvPageFragment.getActivity()))
            .append(comment)
            .append("  ")
            .turnItalicOn()
            .setTextColor(R.color.conv_textLight)
            .append(formattedTime)
            .getSpannable());
        comment = null;
      }
    } else {
      viewHolder.commenter.setVisibility(View.VISIBLE);
      viewHolder.commentTimestamp.setVisibility(View.VISIBLE);
      viewHolder.commentTimestamp.setText(formattedTime);
    }
    if (null != comment) {
      viewHolder.comment.setText(comment);
    }
    final ViewData.PhotoViewData photoViewData = viewData.getCommentedPhoto();
    if (0 == photoViewData.getCount()) {
      viewHolder.commentedImage.setImageBitmap(null);
      viewHolder.commentedImage.setVisibility(View.GONE);
    } else {
      Assert.assertTrue("Comments with photo cannot be combined!", !viewData.isCombined());
      viewHolder.commentedImage.fetchBitmap(mCommentImageDesiredSize,
                                            mCommentImageDesiredSize,
                                            BitmapFetcher.DIMENSIONS_AT_LEAST,
                                            photoViewData.getItem(0),
                                            mConvPageFragment.getAppState());
      viewHolder.commentedImage.setVisibility(View.VISIBLE);
      viewHolder.commentedImage.setOnClickListener(new View.OnClickListener() {
        @Override
        public void onClick(View v) {
          mConvPageFragment.onClickPhoto(mConvViewData.getId(), photoViewData.getItem(0).getId());
        }
      });
    }

    if (viewData.isGroupStart()) {
      viewHolder.threading.setBackgroundResource(R.drawable.convo_thread_start);
    } else if (viewData.isGroupEnd()) {
      viewHolder.threading.setBackgroundResource(R.drawable.convo_thread_end);
    } else if (viewData.isGroupContinuation()) {
      viewHolder.threading.setBackgroundResource(R.drawable.convo_thread_point);
    } else if (viewData.isCombined()) {
      viewHolder.threading.setBackgroundResource(R.drawable.convo_thread_stroke);
    } else {
      viewHolder.threading.setBackground(null);
    }

    return view;
  }

  public View getSharePhotosView(ViewData.ConvViewData.ConvSharePhotosViewData viewData,
                                 View convertView,
                                 ViewGroup parent) {
    View view;
    class ViewHolder  extends ConvViewHolder {
      public ViewHolder(View view) { super(view); }
      public TextView photosSharerText;
      public TextView photosTimestampText;
      public TextView photosLocationText;
      public FullGridView photosView;
    }
    ViewHolder viewHolder;
    final ViewData.PhotoViewData photos = viewData.getPhotos();

    if (null == convertView) {
      view = mInflater.inflate(R.layout.conv_item_share_photos, parent, false);
      viewHolder = new ViewHolder(view);
      viewHolder.photosSharerText = (TextView)view.findViewById(R.id.convItem_sharePhotosSharer);
      viewHolder.photosTimestampText = (TextView)view.findViewById(R.id.convItem_sharePhotosTimestamp);
      viewHolder.photosLocationText = (TextView)view.findViewById(R.id.convItem_sharePhotosLocation);
      viewHolder.photosView = (FullGridView)view.findViewById(R.id.convItem_sharePhotosGrid);
      viewHolder.photosView.setColumnWidth(mSharedImageDesiredSize);
      // Hook into GridView in order to cancel fetches on recycled ImageView's.
      viewHolder.photosView.setRecyclerListener(new AbsListView.RecyclerListener() {
        @Override
        public void onMovedToScrapHeap(View view) {
          ((PhotoImageView) view).cancelFetchRequest();
        }
      });
      setContainerMargins(view);
    } else {
      view = convertView;
      viewHolder = (ViewHolder)view.getTag();
    }

    viewHolder.photosLocationText.setText(viewData.getLocation());
    viewHolder.photosSharerText.setText(viewData.getSharer());
    viewHolder.photosTimestampText.setText(Time.formatTime(viewData.getTimestamp()));

    // TODO(mike): Just a placeholder until a more sophisticated photo layout is implemented.
    viewHolder.photosView.setAdapter(new BaseAdapter() {
      @Override
      public int getCount() {
        return photos.getCount();
      }

      @Override
      public Object getItem(int position) {
        return photos.getItem(position);
      }

      @Override
      public long getItemId(int position) {
        return photos.getItem(position).getId();
      }

      @Override
      public View getView(final int position, View convertView, ViewGroup parent) {
        PhotoImageView photoImageView;
        if (null == convertView) {
          photoImageView = new PhotoImageView(mConvPageFragment.getActivity());
          photoImageView.setScaleType(PhotoImageView.ScaleType.CENTER_CROP);
          photoImageView.setBackgroundColor(mConvPageFragment.getResources().getColor(android.R.color.darker_gray));
          AbsListView.LayoutParams lp = new AbsListView.LayoutParams(mSharedImageDesiredSize, mSharedImageDesiredSize);
          photoImageView.setLayoutParams(lp);
        } else {
          photoImageView = (PhotoImageView) convertView;
          // This has been recycled, check that there are no pending fetches for it.
          photoImageView.assertNoPendingFetch();
        }
        final ViewData.PhotoViewData.PhotoItemViewData photoItem = photos.getItem(position);
        photoImageView.setOnClickListener(new View.OnClickListener() {
          @Override
          public void onClick(View v) {
            mConvPageFragment.onClickPhoto(mConvViewData.getId(), photoItem.getId());
          }
        });

        photoImageView.fetchBitmap(SHARED_IMAGE_SIZE,
                                   SHARED_IMAGE_SIZE,
                                   BitmapFetcher.DIMENSIONS_AT_LEAST,
                                   photoItem,
                                   mConvPageFragment.getAppState());
        return photoImageView;
      }
    });

    return view;
  }

  // Handles any ConvItemViewData which only needs formatted text to be materialized.
  // TODO(Mike): properly format these with different color text using TextView.BufferType.SPANNABLE.
  public View getFormattedTextView(ViewData.ConvViewData.ConvItemViewData viewData,
                                   View convertView,
                                   ViewGroup parent) {
    View view;
    class ViewHolder  extends ConvViewHolder {
      public ViewHolder(View view) { super(view); }
      public TextView formattedText;
    }
    ViewHolder viewHolder;

    if (null == convertView) {
      view = mInflater.inflate(R.layout.conv_item_formatted_text, parent, false);
      viewHolder = new ViewHolder(view);
      viewHolder.formattedText = (TextView)view.findViewById(R.id.convItem_formattedText);
      setContainerMargins(view);
    } else {
      view = convertView;
      viewHolder = (ViewHolder)view.getTag();
    }


    if (viewData instanceof ViewData.ConvViewData.ConvStartedViewData) {
      formatStartedTextView((ViewData.ConvViewData.ConvStartedViewData) viewData,
                            viewHolder.formattedText);
    } else if (viewData instanceof ViewData.ConvViewData.ConvAddFollowersViewData) {
      formatAddFollowersTextView((ViewData.ConvViewData.ConvAddFollowersViewData) viewData,
                                 viewHolder.formattedText);
    } else {
      Assert.fail();
    }

    return view;
  }

  private void formatStartedTextView(ViewData.ConvViewData.ConvStartedViewData viewData,
                                     TextView textView) {
    textView.setText((new SpannableBuilder(mConvPageFragment.getActivity()))
                         .turnBoldOn()
                         .append(viewData.getStartingFollower())
                         .turnBoldOff()
                         .setTextColor(R.color.conv_textLight)
                         .append(" started the conversation ")
                         .turnItalicOn()
                         .append(Time.formatRelativeTime(viewData.getTimestamp(), Time.TimeFormat.TIME_FORMAT_MEDIUM))
                         .getSpannable());
  }

  private void formatAddFollowersTextView(ViewData.ConvViewData.ConvAddFollowersViewData viewData,
                                          TextView textView) {
    String[] followers = viewData.getAddedFollowers();
    SpannableBuilder sb = new SpannableBuilder(mConvPageFragment.getActivity());

    sb.turnBoldOn()
      .append(viewData.getAddingFollower())
      .turnBoldOff()
      .setTextColor(R.color.conv_textLight)
      .append(" added ")
      .setDefaultTextColor()
      .turnBoldOn();

    if (followers.length > 1) {
      sb.append(Utils.enumeratedStringFromStrings(followers, true /* skipLast */))
        .setTextColor(R.color.conv_textLight)
        .turnBoldOff()
        .append(" and ")
        .turnBoldOn()
        .setDefaultTextColor();
    }

    sb.append(followers[followers.length - 1])
      .turnBoldOff()
      .append(" ")
      .turnItalicOn()
      .setTextColor(R.color.conv_textLight)
      .append(Time.formatRelativeTime(viewData.getTimestamp(), Time.TimeFormat.TIME_FORMAT_MEDIUM))
      .getSpannable();

    textView.setText(sb.getSpannable());
  }

  private void setContainerMargins(View view) {
    View itemContainer = view.findViewById(R.id.convItem_container);
    FrameLayout.LayoutParams lp = (FrameLayout.LayoutParams)itemContainer.getLayoutParams();
    lp.setMargins(Math.round(mConvPageFragment.getResources().getDimension(R.dimen.convItem_leftRightMargin)),
                  0,
                  Math.round(mConvPageFragment.getResources().getDimension(R.dimen.convItem_leftRightMargin)),
                  0);
    itemContainer.setLayoutParams(lp);
  }

  private void setItemBackground(int position, View view, ViewData.ConvViewData.ConvItemViewData viewData) {
    // It looks like it's possible to do all this using selectors and custom states in drawable xml, but the following
    //   seems more straight forward.
    int backgroundResource = -1;

    if (0 == position) {
      backgroundResource = R.drawable.conv_item_first;
    } else if (mConvViewData.getCount() - 1 == position) {
      // The view data determines which of two alternating backgrounds should be displayed for this item.
      backgroundResource = viewData.useAlternateBackground() ?
          R.drawable.conv_item_last_alternate :
          R.drawable.conv_item_last;
    } else {
      // The view data determines which of two alternating backgrounds should be displayed for this item.
      backgroundResource = viewData.useAlternateBackground() ?
          R.drawable.conv_item_middle_alternate :
          R.drawable.conv_item_middle;
    }

    ((ConvViewHolder)view.getTag()).setContainerBackground(backgroundResource);
  }
}
