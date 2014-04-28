package co.viewfinder;

import android.database.DataSetObservable;
import android.database.DataSetObserver;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.AsyncTask;
import android.util.Log;
import junit.framework.Assert;

import co.viewfinder.proto.ContactMetadataPB;

import java.io.IOException;
import java.io.InputStream;
import java.util.*;

/**
 * Implement simulated ViewData provider.
 */
public class ViewDataSim implements ViewData {
  private final static String TAG = "Viewfinder.ViewDataSim";
  private final static int MAX_CONV_SUMMARY_PHOTOS = 4;
  private AppState mAppState = null;
  private SimulatedData mSimulatedData = null;
  private ConvSummaryContainer mConvSummaryContainer = null;
  private ContactContainer mContactContainer = null;
  private boolean mReady = false;
  private boolean mStatusSimulatorLaunched = false;

  public ViewDataSim(AppState appState) {
    mAppState = appState;
    mSimulatedData = new SimulatedData();
    mConvSummaryContainer = new ConvSummaryContainer();
    mContactContainer = new ContactContainer(mSimulatedData.getContactNames());
  }

  public int getMaxConvSummaryPhotos() {
    return MAX_CONV_SUMMARY_PHOTOS;
  }

  // Inbox represents a the most unfiltered view of all conversation items available.
  public ConvSummaryViewData getInboxViewData() {
    return mConvSummaryContainer;
  }

  // Given a conversation summary item id, get the conversation.
  public ConvViewData getConvViewDataFromSummaryItemId(long convSummaryItemViewId) {
    return mConvSummaryContainer.getItem(convSummaryItemViewId).getConvViewData();
  }

  public ConvViewData getConvViewDataFromId(long convViewId) {
    // For this implementation, conversations and their summary items share the same ids.
    return getConvViewDataFromSummaryItemId(convViewId);
  }

  @Override
  public ContactViewData getContactViewData() {
    return mContactContainer;
  }

  public void Initialize() {
    mAppState.statusManager().setCurrentStatus("Loading...");
    mSimulatedData.Initialize(250);
    mConvSummaryContainer.Initialize();
    mAppState.statusManager().clearCurrentStatus();
  }

  // Asynchronously launch task to generate simulated data.
  public void Launch() {
    class AsyncSimDataLoader extends AsyncTask<Void, Void, Void> {
      @Override
      protected Void doInBackground(Void... params) {
        Initialize();
        return null;
      }

      @Override
      protected void onPostExecute(Void v) {
        mReady = true;
        mConvSummaryContainer.notifyDataSetChanged();
        mContactContainer.notifyDataSetChanged();
      }
    }

    new AsyncSimDataLoader().execute();
  }

  // Asynchronously launch task to generate simulated data.
  public void simulateStatusChanges() {
    if (!mStatusSimulatorLaunched) {
      new Thread(new Runnable() {
        @Override
        public void run() {
          while (true) {
            try {
              mAppState.statusManager().setCurrentStatus("Testing...");
              Thread.sleep(5000);
              mAppState.statusManager().clearCurrentStatus();
              Thread.sleep(5000);
            } catch (Exception e) {
              break;
            }
          }
        }
      }).start();
      mStatusSimulatorLaunched = true;
    }
  }

  /**
   * Common data container base.
   */
  private abstract class DataContainer<T> implements BaseViewData<T> {
    private final DataSetObservable mDataSetObservable = new DataSetObservable();

    public void registerDataSetObserver(DataSetObserver observer) {
      Log.d(TAG, "registerDataSetObserver: " + observer);
      mDataSetObservable.registerObserver(observer);
    }

    public void unregisterDataSetObserver(DataSetObserver observer) {
      Log.d(TAG, "unregisterDataSetObserver: " + observer);
      mDataSetObservable.unregisterObserver(observer);
    }

    public void notifyDataSetChanged() {
      Log.d(TAG, "notifyDataSetChanged()");
      mDataSetObservable.notifyChanged();
    }
  }

  /**
   * Implements interface consumed by ConvSummaryAdapter to materialize inbox items.
   */
  private class ConvSummaryContainer
      extends DataContainer<ConvSummaryViewData.ConvSummaryItemViewData>
      implements ConvSummaryViewData {
    private ArrayList<ConvSummaryItem> mConvSummaryItems = new ArrayList<ConvSummaryItem>();
    private TreeMap<Long, ConvSummaryItemViewData> mConvSummaryItemLookup =
        new TreeMap<Long, ConvSummaryItemViewData>();

    public ConvSummaryItemViewData getItem(int position) { return mConvSummaryItems.get(position); }
    public ConvSummaryItemViewData getItem(long id) { return mConvSummaryItemLookup.get(id); }
    public int getCount() {
      // Don't appear to have any data until all data is ready.
      // TODO(mike): Need to simulate async updates to this data. Once that's in place, this gate won't be needed.
      return mReady ? mConvSummaryItems.size() : 0;
    }

    public void Initialize() {
      for (int iConv = 0; iConv < mSimulatedData.getConvCount(); iConv++) {
        SimulatedData.Conv conv = mSimulatedData.getConv(iConv);
        ConvSummaryItem item = new ConvSummaryItem(conv, iConv);
        mConvSummaryItemLookup.put(item.getId(), item);
        mConvSummaryItems.add(item);
      }
    }

    private class ConvSummaryItem implements ConvSummaryItemViewData {
      private long mId;
      private SimulatedData.Conv mConv;
      private int mPosition = 0;
      private ConvViewData mConvViewData = null;

      public ConvSummaryItem(SimulatedData.Conv conv, int position) {
        mId = mSimulatedData.allocNextId();
        mConv = conv;
        mPosition = position;
        mConvViewData = new ConvContainer(mConv, mId);
      }

      public long getId() { return mId; }
      public int getPosition() { return mPosition; }
      public String getTitle() { return mConv.getHeader().title; }
      public String[] getFollowers() { return mConv.getHeader().followers; }
      public int getPhotoCount() { return mConv.photoCount; }
      public int getCommentCount() { return mConv.commentCount; }
      public boolean isAutoSaving() { return mConv.getHeader().isAutoSaving; }
      public boolean isMuted() { return mConv.getHeader().isMuted; }
      public long getLastUpdateTime() { return mConv.getLastUpdateTime(); }
      public ConvViewData getConvViewData() { return mConvViewData; }
      public boolean isUnviewed() { return false; }

      public PhotoViewData getConvSummaryItemPhotos() {
        return new PhotoViewContainer(mConv.getConvSummaryPhotoItems());
      }
    }
  }

  /**
   * Implements interface consumed by ConvAdapter to materialize conversation items.
   */
  private class ConvContainer extends DataContainer<ConvViewData.ConvItemViewData>
                                      implements ConvViewData {
    private long mId;
    private SimulatedData.Conv mConv;
    private ArrayList<ConvItem> mItems;
    private TreeMap<Long, ConvItemViewData> mConvItemLookup =
        new TreeMap<Long, ConvItemViewData>();

    public int getPosition() { return mConv.position; }
    public int getCount() { return mConv.items.size(); }
    public long getId() { return mId; }
    public ConvItemViewData getItem(long id) { return mConvItemLookup.get(id); }

    public ConvItemViewData getItem(int position) { return mItems.get(position); }
    public PhotoViewData getAllPhotos() { return new PhotoViewContainer(mConv.getAllConvPhotoItems()); }

    public ConvContainer(SimulatedData.Conv conv, long id) {
      mId = id;
      mConv = conv;
      buildItems();
    }

    private void buildItems() {
      mItems = new ArrayList<ConvItem>(mConv.items.size());

      for (int iPosition = 0; iPosition < mConv.items.size(); iPosition++) {
        SimulatedData.Conv.Item simItem = mConv.items.get(iPosition);
        ConvItem item = null;
        if (simItem instanceof SimulatedData.Conv.Header) {
          item = new ConvHeader((SimulatedData.Conv.Header)simItem);
        } else if (simItem instanceof SimulatedData.Conv.Started) {
          item = new ConvStarted((SimulatedData.Conv.Started)simItem);
        } else if (simItem instanceof SimulatedData.Conv.Comment) {
          item = new ConvComment((SimulatedData.Conv.Comment)simItem);
        } else if (simItem instanceof SimulatedData.Conv.SharePhotos) {
          item = new ConvSharePhotos((SimulatedData.Conv.SharePhotos)simItem);
        } else if (simItem instanceof SimulatedData.Conv.AddFollowers) {
          item = new ConvAddFollowers((SimulatedData.Conv.AddFollowers)simItem);
        } else {
          Assert.fail("unexpected type");
        }
        mConvItemLookup.put(item.getId(), item);
        mItems.add(item);
      }

      // First, determine visually combined comments.
      ConvComment prevItem = null;
      for (ConvItem item: mItems) {
        if (ConvItemType.COMMENT == item.getItemType()) {
          ConvComment curItem = (ConvComment)item;
          // Was the previous item a comment?
          if (prevItem != null) {
            // Was it authored by the same person?
            if (prevItem.getCommenter().compareTo(curItem.getCommenter()) == 0) {
              // Was the previous comment less than an hour ago?
              if (mSimulatedData.mRand.nextBoolean()) {
                // Only if no commented photo will we combine this with previous comment.
                if (!curItem.hasCommentedPhoto()) {
                  curItem.setCombined(true);
                  curItem.setTimestampAdded(mSimulatedData.mRand.nextBoolean());
                }
              }
            }
          }
          prevItem = curItem;
        } else {
          prevItem = null;
        }
      }

      // Now, determine visual threading indication.
      // This doesn't even come close to what would really be displayed, but it will exercise the
      //   visual elements.
      for (int i = 0; i < mItems.size(); i++) {
        ConvComment prevComment = i > 0 ? mItems.get(i-1).asComment() : null;
        ConvComment curComment = mItems.get(i).asComment();
        ConvComment nextComment = i < mItems.size() - 1 ? mItems.get(i+1).asComment() : null;

        if (null != curComment) {
          if (null != prevComment) {
            if (null != nextComment) {
              curComment.setGroupContinuation(true);
            } else {
              curComment.setGroupEnd(true);
            }
          } else if (null != nextComment) {
            curComment.setGroupStart(true);
          }
        }
      }

      // Now, apply alternateBackground:
      boolean alternateBackgroundOn = true;
      for (ConvItem item : mItems) {
        // Comment continuations do not alternate backgrounds.
        if (ConvItemType.COMMENT != item.getItemType() ||
            !((ConvComment)item).isCombined()) {
          alternateBackgroundOn = !alternateBackgroundOn;
        }
        item.setUseAlternateBackground(alternateBackgroundOn);
      }
    }

    public PhotoViewData getCoverPhoto() {
      if (null != mConv.getCoverPhotoItem()) {
        return new PhotoViewContainer(mConv.getCoverPhotoItem());
      }
      return new PhotoViewContainer();
    }

    private abstract class ConvItem implements ConvItemViewData {
      private long mId;
      private boolean mUseAlternateBackground = false;

      public ConvItem() {
        mId = mSimulatedData.allocNextId();
      }

      public long getId() { return mId; }
      public long getTimestamp() { return getConvItem().timestamp; }
      public int getPosition() { return getConvItem().position; }
      public boolean isUnviewed() { return false; }
      public boolean useAlternateBackground() { return mUseAlternateBackground; }
      protected abstract SimulatedData.Conv.Item getConvItem();

      void setUseAlternateBackground(boolean useAlternateBackground) {
        mUseAlternateBackground = useAlternateBackground;
      }

      public ConvComment asComment() { return ConvItemType.COMMENT == getItemType() ? (ConvComment)this : null; }
    }

    private class ConvHeader extends ConvItem
                                     implements ConvHeaderViewData {
      private SimulatedData.Conv.Header mConvItem;
      protected SimulatedData.Conv.Item getConvItem() { return mConvItem; }

      public ConvItemType getItemType() { return ConvItemType.HEADER; }
      public String getTitle() { return mConvItem.title; }
      public String[] getFollowers() { return mConvItem.followers; }
      public boolean isAutoSaving() { return mConvItem.isAutoSaving; }
      public boolean isMuted() { return mConvItem.isMuted; }

      public ConvHeader(SimulatedData.Conv.Header convItem) {
        mConvItem = convItem;
      }
    }

    private class ConvStarted extends ConvItem
                                      implements ConvStartedViewData {
      private SimulatedData.Conv.Started mConvItem;

      protected SimulatedData.Conv.Item getConvItem() { return mConvItem; }

      public ConvItemType getItemType() { return ConvItemType.STARTED; }
      public String getStartingFollower() { return mConvItem.follower; }

      public ConvStarted(SimulatedData.Conv.Started convItem) {
        mConvItem = convItem;
      }
    }

    private class ConvComment extends ConvItem
                                      implements ConvCommentViewData {
      private SimulatedData.Conv.Comment mConvItem;
      private boolean mIsCombined = false;
      private boolean mIsTimestampAdded = false;
      private boolean mIsGroupStart = false;
      private boolean mIsGroupContinuation = false;
      private boolean mIsGroupEnd = false;

      protected SimulatedData.Conv.Item getConvItem() { return mConvItem; }

      public ConvItemType getItemType() { return ConvItemType.COMMENT; }
      public String getComment() { return mConvItem.comment; }
      public String getCommenter() { return mConvItem.commenter; }
      public PhotoViewData getCommentedPhoto() {
        if (null != mConvItem.commentedPhoto) {
          return new PhotoViewContainer(mConvItem.commentedPhoto);
        }
        return new PhotoViewContainer();
      }
      public boolean isCombined() { return mIsCombined; }
      public boolean isTimestampAppended() { return mIsTimestampAdded; }
      public boolean isGroupStart() { return mIsGroupStart; }
      public boolean isGroupContinuation() { return mIsGroupContinuation; }
      public boolean isGroupEnd() { return mIsGroupEnd; }
      public boolean hasCommentedPhoto() { return null != mConvItem.commentedPhoto; }

      void setCombined(boolean combined) { mIsCombined = combined; }
      void setTimestampAdded(boolean timestampAdded) { mIsTimestampAdded = timestampAdded; }
      void setGroupStart(boolean groupStart) { mIsGroupStart = groupStart; }
      void setGroupContinuation(boolean groupContinuation) { mIsGroupContinuation = groupContinuation; }
      void setGroupEnd(boolean groupEnd) { mIsGroupEnd = groupEnd; }

      public ConvComment(SimulatedData.Conv.Comment convItem) {
        mConvItem = convItem;
      }
    }

    private class ConvSharePhotos extends ConvItem
                                           implements ConvSharePhotosViewData {
      private SimulatedData.Conv.SharePhotos mConvItem;

      protected SimulatedData.Conv.Item getConvItem() { return mConvItem; }

      public ConvItemType getItemType() { return ConvItemType.SHARE_PHOTOS; }
      public PhotoViewData getPhotos() { return new PhotoViewContainer(mConvItem.photos); }
      public String getSharer() { return mConvItem.sharer; }

      public ConvSharePhotos(SimulatedData.Conv.SharePhotos convItem) {
        mConvItem = convItem;
      }

      public String getLocation() {
        // For now, just pick the first one.
        for(PhotoItem photoItem : mConvItem.photos) {
          String location = photoItem.getLocation();
          if (null != location) {
            return location;
          }
        }
        if (mConvItem.photos.length > 1) {
          return String.format("%d photos without locations", mConvItem.photos.length);
        }
        return "1 photo without location";
      }

      public boolean isSaved() {
        for(PhotoItem photoItem : mConvItem.photos) {
          if (!photoItem.isSaved()) return false;
        }
        return true;
      }
    }

    private class ConvAddFollowers extends ConvItem
                                             implements ConvAddFollowersViewData {
      private SimulatedData.Conv.AddFollowers mConvItem;

      protected SimulatedData.Conv.Item getConvItem() { return mConvItem; }

      public ConvItemType getItemType() { return ConvItemType.ADD_FOLLOWERS; }
      public String getAddingFollower() { return mConvItem.addingFollower; }
      public String[] getAddedFollowers() { return mConvItem.followers; }

      public ConvAddFollowers(SimulatedData.Conv.AddFollowers convItem) {
        mConvItem = convItem;
      }
    }
  }

  /**
   * Implements interface for accessing different sized bitmaps of the same image.
   */
  private class PhotoViewContainer
      extends DataContainer<PhotoViewData.PhotoItemViewData>
      implements  PhotoViewData {
    private PhotoItemView[] mPhotoViews;
    private TreeMap<Long, PhotoItemView> mPhotoItemLookup = new TreeMap<Long, PhotoItemView>();

    public int getCount() { return mPhotoViews.length; }
    public PhotoItemViewData getItem(int i) { return mPhotoViews[i]; }
    public PhotoItemViewData getItem(long id) { return mPhotoItemLookup.get(id); }

    public PhotoViewContainer() {
      mPhotoViews = new PhotoItemView[0];
    }
    public PhotoViewContainer(PhotoItem photoItem) {
      mPhotoViews = new PhotoItemView[1];
      mPhotoViews[0] = new PhotoItemView(photoItem, 0);
      mPhotoItemLookup.put(mPhotoViews[0].getId(), mPhotoViews[0]);
    }
    public PhotoViewContainer(PhotoItem[] photoItems) {
      mPhotoViews = new PhotoItemView[photoItems.length];
      for (int i = 0; i < photoItems.length; i++) {
        mPhotoViews[i] = new PhotoItemView(photoItems[i], i);
        mPhotoItemLookup.put(mPhotoViews[i].getId(), mPhotoViews[i]);
      }
    }

    private class PhotoItemView implements PhotoItemViewData {
      private PhotoItem mPhotoItem;
      private int mPosition;

      public PhotoItemView(PhotoItem photoItem, int position) {
        mPhotoItem = photoItem;
        mPosition = position;
      }

      public long getId() { return mPhotoItem.getId(); }
      public boolean isSaved() { return mPhotoItem.isSaved(); }
      public String getLocation() { return mPhotoItem.getLocation(); }
      public long getTimestamp() { return mPhotoItem.getTimestamp(); }
      public float getAspectRatio() { return mPhotoItem.getAspectRatio(); }
      public int getPosition() { return mPosition; }

      public String getPathToImage(int width, int height) {
        String pathToImage;
        // TODO(mike): use metadata that should be available to make a decision about which image path to return.
        if ((width > 200) || (height > 200)) {
          // get larger image:
          pathToImage = mSimulatedData.getSimulatedPhotoAssets().getMediumPath(mPhotoItem.getPhotoId());
        } else {
          // get smaller.
          pathToImage = mSimulatedData.getSimulatedPhotoAssets().getThumbnailPath(mPhotoItem.getPhotoId());
        }
        return pathToImage;
      }

      public ConvSummaryViewData getRelatedConversations() {
        // TODO(mike): Add related conversation functionality
        return null;
      }
    }
  }

  private class ContactContainer
          extends DataContainer<ContactMetadataPB.ContactMetadata>
          implements ContactViewData {

    private ContactMetadataPB.ContactMetadata[] mContactItems;
    private TreeMap<Long, ContactMetadataPB.ContactMetadata> mContactItemLookup = new TreeMap<Long, ContactMetadataPB.ContactMetadata>();

    public ContactContainer() {
      mContactItems = new ContactMetadataPB.ContactMetadata[0];
    }

    public ContactContainer(String[] rawContacts) {
      ArrayList<String> contacts = new ArrayList<String>(Arrays.asList(rawContacts));
      Collections.sort(contacts);

      mContactItems = new ContactMetadataPB.ContactMetadata[contacts.size()];
      for (int i = 0; i < mContactItems.length; i++) {
        String email = contacts.get(i).replace(' ', '.') + "@emailscrubbed.com";
        ContactMetadataPB.ContactMetadata.Builder builder = ContactMetadataPB.ContactMetadata.newBuilder();
        ContactMetadataPB.ContactIdentityMetadata.Builder idBuilder = ContactMetadataPB.ContactIdentityMetadata.newBuilder();

        idBuilder.setUserId((long)i);
        idBuilder.setIdentity("Email:" + email);
        idBuilder.setDescription("work");

        builder.addIdentities(idBuilder.build());
        builder.setPrimaryIdentity(idBuilder.getIdentity());
        builder.setUserId((long)i);
        builder.setContactSource("gm");
        builder.setEmail(email);
        builder.setName(contacts.get(i));

        mContactItems[i] = builder.build();

        // mContactItems[i] = new ContactItemView((long)i, contacts[i], i);
        mContactItemLookup.put(mContactItems[i].getUserId(), mContactItems[i]);
      }
    }

    public int count() {
      return getCount();
    }

    @Override
    public int getCount() {
      return mContactItems.length;
    }

    @Override
    public void setNickname(long contactId, String nickname) {
      ContactMetadataPB.ContactMetadata.Builder builder = getItem(contactId).toBuilder();
      builder.setNickname(nickname);
      mContactItems[(int) contactId] = builder.build();
      mContactItemLookup.put(contactId, mContactItems[(int) contactId]);
      notifyDataSetChanged();
    }

    @Override
    public ContactMetadataPB.ContactMetadata getItem(long id) {
      return mContactItemLookup.get(id);
    }

    @Override
    public ContactMetadataPB.ContactMetadata getItem(int position) {
      return mContactItems[position];
    }
  }


  /**
   * Generates/simulates conversation data.
   */
  private class SimulatedData {
    private long mLastId = 0;
    private SimulatedPhotoAssets mSimulatedPhotoAssets = new SimulatedPhotoAssets();
    private Random mRand = new Random();
    private ArrayList<Conv> mConvs = new ArrayList<Conv>();

    private final String[] POSSIBLE_FOLLOWERS =
        {"Brian McGinnis",
         "Chris Schoenbohm",
         "Spencer Kimball",
         "Pete Mattis",
         "Andy Kimball",
         "Brett Eisenman",
         "Harry Clarke",
         "Matt Tracy",
         "Mike Purtell",
         "Ben Darnell",
         "Marc Berhault",
         "Greg Vandenberg",
         "Dan Shin" };
    private final String[] POSSIBLE_PHRASES =
        {"Timer got too hot! \uD83D\uDE0A",
         "From down under.",
         "Tiles are in this year.",
         "That's how it's done!!!",
         "Why would you want that?",
         "Why wouldn't you do that?",
         "Heading for Scotland.",
         "Tell me when you get there.",
         "I've never seen anything like this.",
         "When is everyone arriving?",
         "Dallas was quite a show.",
         "Dallas, we have a problem!",
         "Tomorrow is the longest day of the year but not in terms of the number of minutes in the day, but in terms of how much sunlight we will get.",
         "Typical!",
         "",
         "I have no idea what that is.",
         "Orange is the new blue.",
         "The ocean has many pirates.",
         "The Seattle Seahawks played last Thursday.",
         "Look at the damage to the siding.",
         "I'm almost at a loss for words.",
         "Two more days until shuffle board season starts.",
         "Apples and oranges are good sources of fiber!",
         "Go home, now!",
         "Write on the chalk board: I really enjoy math.",
        };

    private final String[] POSSIBLE_LOCATIONS =
       {"Seattle, Washington",
         "New York, New York",
         "Cedar Rapids, Iowa",
         "Bellevue, Washington",
         null,  // represents absense of location data.
         "Chicago, Illinois",
         "Miami, Florida",
         "Dallas, Texas",
         "Los Angeles, California",
       };

    public void Initialize(int convCount) {
      generateSimulatedData(convCount);
    }

    public long allocNextId() { return ++mLastId; }

    private SimulatedPhotoAssets getSimulatedPhotoAssets() { return mSimulatedPhotoAssets; }

    private class Conv {
      private ArrayList<PhotoItem> mAllConvPhotoItems = new ArrayList<PhotoItem>();
      private PhotoItem[] mConvSummaryPhotoItems = null;
      private PhotoItem mCoverPhoto = null;
      private int position;
      private ArrayList<Item> items = new ArrayList<Item>();
      private int photoCount = 0;
      private int commentCount = 0;

      public Header getHeader() { return (Header)items.get(0); }
      public long getLastUpdateTime() { return items.get(items.size()-1).timestamp; }

      public PhotoItem[] getAllConvPhotoItems() {
        return mAllConvPhotoItems.toArray(new PhotoItem[mAllConvPhotoItems.size()]);
      }
      public PhotoItem[] getConvSummaryPhotoItems() {
        // Collect last MAX_CONV_SUMMARY_PHOTOS photos in reverse order into mConvSummaryPhotoItems.
        if (null == mConvSummaryPhotoItems) {
          int allPhotosCount = mAllConvPhotoItems.size();
          mConvSummaryPhotoItems = new PhotoItem[Math.min(MAX_CONV_SUMMARY_PHOTOS, allPhotosCount)];
          for (int i = 0; i < mConvSummaryPhotoItems.length; i++) {
            mConvSummaryPhotoItems[i] = mAllConvPhotoItems.get(allPhotosCount - 1 - i);
          }
        }
        return mConvSummaryPhotoItems;
      }
      public PhotoItem getCoverPhotoItem() { return mCoverPhoto; }

      public class Item {
        public int position;
        public long timestamp;
      }

      public class Header extends Item {
        public String title;
        public String[] followers;
        public boolean isAutoSaving;
        public boolean isMuted;
      }
      public class Started extends Item {
        public String follower;
      }
      public class Comment extends Item {
        public String commenter;
        public String comment;
        public PhotoItem commentedPhoto;
      }
      public class SharePhotos extends Item {
        public String sharer;
        public PhotoItem[] photos;
      }
      public class AddFollowers extends Item {
        public String addingFollower;
        public String[] followers;
      }

      private Header generateHeader(long timestamp) {
        Conv.Header header = new Conv.Header();
        header.position = 0;
        header.timestamp = timestamp;
        header.title = getRandomPhrase();
        header.followers = getRandomFollowers();
        header.isAutoSaving = mRand.nextBoolean();
        header.isMuted = mRand.nextBoolean();
        return header;
      }

      private Started generateStarted(long timestamp, String[] followers) {
        Conv.Started started = new Conv.Started();
        started.position = 1;
        started.timestamp = timestamp;
        started.follower = followers[mRand.nextInt(followers.length)];
        return started;
      }

      private Comment generateComment(long timestamp, int position, String lastCommenter) {
        Conv.Comment comment = new Conv.Comment();
        comment.position = position;
        comment.timestamp = timestamp;
        if ((null != lastCommenter) && mRand.nextBoolean()) {
          comment.commenter = lastCommenter;
        } else {
          comment.commenter = getRandomFollower();
        }
        comment.comment = getRandomPhrase();
        if ((mRand.nextInt(100) < 25) && (mAllConvPhotoItems.size() > 0)) {
          comment.commentedPhoto =  mAllConvPhotoItems.get(mRand.nextInt(mAllConvPhotoItems.size()));
        }
        return comment;
      }

      private SharePhotos generateSharePhotos(long timestamp, int position) {
        Conv.SharePhotos sharePhotos = new Conv.SharePhotos();
        sharePhotos.position = position;
        sharePhotos.timestamp = timestamp;
        sharePhotos.photos = getRandomPhotoItems(9);
        sharePhotos.sharer = getRandomFollower();
        if (null == mCoverPhoto) mCoverPhoto = sharePhotos.photos[0];
        mAllConvPhotoItems.addAll(Arrays.asList(sharePhotos.photos));
        return sharePhotos;
      }

      private AddFollowers generateAddFollowers(long timestamp, int position) {
        Conv.AddFollowers addFollowers = new Conv.AddFollowers();
        addFollowers.position = position;
        addFollowers.timestamp = timestamp;
        addFollowers.addingFollower = getRandomFollower();
        addFollowers.followers = getRandomFollowers(); // Note: may not make sense because of dups.
        return addFollowers;
      }
    }

    private void generateSimulatedData(int convCount) {
      String lastCommenter = null;

      for (int iConv = 0; iConv < convCount; iConv++) {
        Conv conv = new Conv();
        conv.position = iConv;
        int itemCount = mRand.nextInt(50) + 2; // 1 for header item and 1 for started item.
        long now = new Date().getTime() - (1000 * 60 * 60 * 24);  // one day ago.
        long increment = (1000 * 60 * 60 * 24) / itemCount;
        conv.items.add(conv.generateHeader(now));
        conv.items.add(conv.generateStarted(now, ((Conv.Header)conv.items.get(0)).followers));
        // Already added first two items, so skip those positions.
        for (int iPosition = 2; iPosition < itemCount; iPosition++) {
          now += increment;
          Conv.Item item = null;
          switch(getRandomItemType()) {
            case COMMENT:
              item = conv.generateComment(now, iPosition, lastCommenter);
              lastCommenter = ((Conv.Comment)item).commenter;
              conv.commentCount++;
              break;
            case SHARE_PHOTOS:
              item = conv.generateSharePhotos(now, iPosition);
              conv.photoCount += ((Conv.SharePhotos)item).photos.length;
              break;
            case ADD_FOLLOWERS:
              item = conv.generateAddFollowers(now, iPosition);
              break;
            default:
              Assert.fail();
          }
          conv.items.add(item);
        }
        mConvs.add(conv);
      }
    }

    private String[] getRandomFollowers() {
      int count = mRand.nextInt(POSSIBLE_FOLLOWERS.length) + 1;
      String[] followers = new String[count];
      for (int i = 0; i < count; i++) {
        followers[i] = getRandomFollower();
      }
      return followers;
    }

    private String getRandomFollower() { return POSSIBLE_FOLLOWERS[mRand.nextInt(POSSIBLE_FOLLOWERS.length)]; }
    private String getRandomPhrase() { return POSSIBLE_PHRASES[mRand.nextInt(POSSIBLE_PHRASES.length)]; }

    private PhotoItem[] getRandomPhotoItems(int max) {
      PhotoItem[] photoItems = new PhotoItem[mRand.nextInt(max) + 1]; // Get at least one.

      for (int i = 0; i < photoItems.length; i++) {
        // Note: may get duplicates.
        photoItems[i] = getRandomPhotoItem();
      }
      return photoItems;
    }

    private PhotoItem getRandomPhotoItem() {
      String photoId = getRandomPhotoId();
      return new PhotoItem(photoId,
                           getRandomPhotoLocation(),
                           mRand.nextBoolean(),
                           getRandomTimestamp(),
                           mSimulatedPhotoAssets.getAspectRatio(photoId));
    }

    private long getRandomTimestamp() {
      // return some random time in the previous 24 hours.
      return new Date().getTime() - mRand.nextInt((int)(Time.MS_PER_HOUR * Time.HOURS_PER_DAY));
    }

    private String getRandomPhotoId() {
      String[] allPhotoIds = mSimulatedPhotoAssets.getAllPhotoIds();
      return allPhotoIds[mRand.nextInt(allPhotoIds.length)];
    }

    private String getRandomPhotoLocation() {
      return POSSIBLE_LOCATIONS[mRand.nextInt(POSSIBLE_LOCATIONS.length)];
    }

    private ConvViewData.ConvItemType getRandomItemType() {
      int typeCount = ConvViewData.ConvItemType.values().length;
      // Disregard the first two.
      return ConvViewData.ConvItemType.values()[mRand.nextInt(typeCount-2)+2];
    }

    public int getConvCount() { return mConvs.size(); }
    public Conv getConv(int iPosition) { return mConvs.get(iPosition); }
    public final String[] getContactNames() { return POSSIBLE_FOLLOWERS; }
  }

  private class PhotoItem {
    private long mId;
    private String mPhotoId;
    private String mLocation;
    private boolean mIsSaved;
    private long mTimestamp;
    private float mAspectRatio;

    public PhotoItem(String photoId, String location, boolean isSaved, long timestamp, float aspectRatio) {
      mId = mSimulatedData.allocNextId();
      mPhotoId = photoId;
      mLocation = location;
      mIsSaved = isSaved;
      mTimestamp = timestamp;
      mAspectRatio = aspectRatio;
    }

    public long getId() { return mId; }
    public String getPhotoId() { return mPhotoId; }
    public String getLocation() { return mLocation; }
    public long getTimestamp() { return mTimestamp; }
    public boolean isSaved() { return mIsSaved; }
    public float getAspectRatio() { return mAspectRatio; }

  }

  /**
   * Simulates photo assets by loading photos that are packaged with the app.
   */
  private class SimulatedPhotoAssets {
    private static final String PHOTO_FILES_PATH = "test/files/photos/";
    private static final String MEDIUM_SIZE_PHOTO_FILES_PATH = PHOTO_FILES_PATH + "medium";
    private static final String THUMBNAIL_SIZE_PHOTO_FILES_PATH = PHOTO_FILES_PATH + "thumb";
    private String[] mAllPhotoIds = null;
    private HashMap<String, Float> mAspectRatioLookup = new HashMap<String, Float>();

    public SimulatedPhotoAssets() {
      mAllPhotoIds = getPhotoFileNames(MEDIUM_SIZE_PHOTO_FILES_PATH);
      for (String photoId : mAllPhotoIds) {
        mAspectRatioLookup.put(photoId, determineAspectRatio(photoId));
      }
    }

    public String[] getAllPhotoIds() { return mAllPhotoIds; }
    public float getAspectRatio(String photoId) { return mAspectRatioLookup.get(photoId); }

    private String[] getPhotoFileNames(String dirPath) {
      String[] fileNames = null;
      try {
        fileNames = mAppState.getAssets().list(dirPath);
      } catch (IOException e) {
        e.printStackTrace();
      }
      return fileNames;
    }

    private String getMediumPath(String photoId) { return MEDIUM_SIZE_PHOTO_FILES_PATH + "/" + photoId; }
    private String getThumbnailPath(String photoId) { return THUMBNAIL_SIZE_PHOTO_FILES_PATH + "/" + photoId; }

    private float determineAspectRatio(String photoId) {
      BitmapFactory.Options options = new BitmapFactory.Options();
      options.inJustDecodeBounds = true;
      getBitmapFromPath(MEDIUM_SIZE_PHOTO_FILES_PATH + "/" + photoId, options);
      return (float)options.outWidth/(float)options.outHeight;
    }

    private Bitmap getBitmapFromPath(String path, BitmapFactory.Options options) {
      Bitmap bitmap = null;
      InputStream file = null;

      try {
        file = mAppState.getAssets().open(path);
        bitmap = BitmapFactory.decodeStream(file, null, options);
      } catch (IOException e) {
        e.printStackTrace();
      } finally {
        if (null != file) {
          try {
            file.close();
          } catch(IOException e) {
            e.printStackTrace();
          }
        }
      }
      return bitmap;
    }
  }
}
