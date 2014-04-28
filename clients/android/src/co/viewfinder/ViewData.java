// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.database.DataSetObserver;
import co.viewfinder.proto.ContactMetadataPB;

/**
 * Defines interface between view and data model.
 * There are currently 3 types of ViewData and their containers:
 * 1) ConvSummary
 * 2) Conv
 * 3) Photo
 * *) Contact  -- to be added.
 */
public interface ViewData {

  /**
   * Represents container types.
   */
  public interface BaseViewData<T> {

    /**
     * Count of of items in container.
     * Value is valid until data change notification.
     */
    int getCount();

    /**
     * Retrieve item by id.  May be null if entity no longer exists or is no longer 'visible'.
     * Item id is meant to always reference the same entity, even after a data change notification.
     */
    T getItem(long id);

    /**
     * Retrieve item by it's current position within the container.  Null if position has no item.
     */
    T getItem(int position);

    /**
     * Register for data change notifications.
     * This is used to drive refresh of ListViews, PagerViews, etc.
     * A data change notification invalidates all data previously retrieved from container.
     */
    void registerDataSetObserver(DataSetObserver observer);

    /**
     * Unregister for data change notifications.
     */
    void unregisterDataSetObserver(DataSetObserver observer);
  }

  /**
   * Represents container item types.
   */
  public interface BaseItemViewData {
    /**
     * Position of item within container that item was retrieved from.
     * Value is valid until data change notification.
     */
    int getPosition();

    /**
     * Id of item within container that item was retrieved from.
     * Value is stable, but item may not exists after data change notification.
     */
    long getId();
  }

  /**
   * Primary interface consumed by conversation summary view.
   */
  public interface ConvSummaryViewData extends BaseViewData<ConvSummaryViewData.ConvSummaryItemViewData> {

    public interface ConvSummaryItemViewData extends BaseItemViewData {
      String getTitle();
      String[] getFollowers();  // Ordered for display.
      PhotoViewData getConvSummaryItemPhotos(); // Last N photos ordered for display.
      int getPhotoCount();  // Count of visible photos in conversation.
      int getCommentCount();
      boolean isAutoSaving();
      boolean isMuted();
      long getLastUpdateTime();
      boolean isUnviewed();
      ConvViewData getConvViewData();  // Used when opening conversation view.
    }
  }

  /**
   * Primary interface consumed by conversation view.
   */
  public interface ConvViewData extends BaseViewData<ConvViewData.ConvItemViewData>,
                                                BaseItemViewData {
    enum ConvItemType {
      HEADER,
      STARTED,
      COMMENT,
      SHARE_PHOTOS,
      ADD_FOLLOWERS;

      private static final int COUNT = ConvItemType.values().length;
      public static int getCount() { return COUNT; }
    }

    public interface ConvItemViewData extends BaseItemViewData {
      ConvItemType getItemType();
      long getTimestamp();
      boolean isUnviewed();
      boolean useAlternateBackground();
    }

    public interface ConvHeaderViewData extends ConvItemViewData {
      String getTitle();
      String[] getFollowers();
      boolean isAutoSaving();
      boolean isMuted();
    }

    public interface ConvStartedViewData extends ConvItemViewData {
      String getStartingFollower();
    }

    public interface ConvCommentViewData extends ConvItemViewData {
      String getCommenter();
      String getComment();
      PhotoViewData getCommentedPhoto();
      boolean isCombined();  // Visually combine with previous row.
      boolean isTimestampAppended();  // If combined, also append timestamp.
      boolean isGroupStart();
      boolean isGroupContinuation();
      boolean isGroupEnd();
    }

    public interface ConvSharePhotosViewData extends ConvItemViewData {
      boolean isSaved();
      String getSharer();
      String getLocation();
      PhotoViewData getPhotos();
    }

    public interface ConvAddFollowersViewData extends ConvItemViewData {
      String getAddingFollower();
      String[] getAddedFollowers();
    }

    PhotoViewData getCoverPhoto();
    PhotoViewData getAllPhotos();
  }

  /**
   * Interface for accessing image data.
   */
  public interface PhotoViewData extends BaseViewData<PhotoViewData.PhotoItemViewData> {

    public interface PhotoItemViewData extends BaseItemViewData {
      float getAspectRatio();
      boolean isSaved();
      String getLocation();
      long getTimestamp();
      String getPathToImage(int idealWidth, int idealHeight);
      ConvSummaryViewData getRelatedConversations();
    }
  }

  /**
   * Interface for accessing contact data.
   */
  public interface ContactViewData extends BaseViewData<ContactMetadataPB.ContactMetadata> {
    void setNickname(long contactId, String nickname);
  }

  // Retrieve the collection of all ConvSummaryItems.
  ConvSummaryViewData getInboxViewData();

  ConvViewData getConvViewDataFromSummaryItemId(long convSummaryItemViewId);
  ConvViewData getConvViewDataFromId(long convViewId);

  // Max number of photos that will be part of a conversation summary item.
  int getMaxConvSummaryPhotos();

  ContactViewData getContactViewData();
}
