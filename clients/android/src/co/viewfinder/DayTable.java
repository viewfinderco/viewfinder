// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis
package co.viewfinder;

import android.util.Log;
import co.viewfinder.proto.DayMetadataPB.SummaryMetadata;
import co.viewfinder.proto.DayMetadataPB.SummaryRow;
import co.viewfinder.proto.DayMetadataPB.ViewpointSummaryMetadata;
import com.google.protobuf.InvalidProtocolBufferException;
import java.lang.Double;
import java.lang.Long;
import java.lang.Runnable;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import junit.framework.Assert;

public class DayTable {
  private static final String TAG = "viewfinder.DayTable";

  public static final class ConversationSummary {
    private static final Comparator<SummaryRow> kSummaryRowCompare =
        new Comparator<SummaryRow>() {
      public int compare(SummaryRow a, SummaryRow b) {
        // Note that we want a larger day timestamp to compare less than a
        // smaller day timestamp, thus "b" is the first parameter and "a" is
        // the second.
        int c = Double.compare(b.getDayTimestamp(), a.getDayTimestamp());
        if (c != 0) {
          return c;
        }
        // Long.compare() does not exist on Android?
        return Long.valueOf(a.getIdentifier()).compareTo(Long.valueOf(b.getIdentifier()));
      }
    };

    private final DB mDB;
    private final SummaryMetadata mSummary;

    public ConversationSummary(DB db) {
      mDB = db;
      // TODO: share key definitions.
      mSummary = db.getProto("m/conversation_summary", SummaryMetadata.PARSER);
      if (mSummary == null) {
        // TODO: figure out what to do here.
        Log.w(TAG, "No conversation summary found");
        return;
      }
      Log.i(TAG, "Got conversation summary:\n" + mSummary);
    }

    public int getPhotoCount() {
      if (mSummary == null) {
        return 0;
      }
      return mSummary.getPhotoCount();
    }

    public int getRowCount() {
      if (mSummary == null) {
        return 0;
      }
      return mSummary.getRowsCount();
    }

    public int getUnviewedInboxCount() {
      if (mSummary == null) {
        return 0;
      }
      return mSummary.getUnviewedCount();
    }

    // Returns the row index of the specified viewpoint.
    public int getViewpointRowIndex(long viewpointId) {
      if (mSummary == null) {
        return -1;
      }

      // This algorithm is based on the C++ code in
      // DayTable::Summary::GetSummaryRowIndex() and
      // DayTable::ConversationSummary::GetViewpointRowIndex().
      SummaryRow key = getSummaryRowKey(viewpointId);
      int index = Collections.binarySearch(
          mSummary.getRowsList(), key, kSummaryRowCompare);
      if (index < 0) {
        // TODO(spencer): while there is a bug which sometimes causes the
        //   summary protobuf to get out of date, do a linear search for the
        //   missing viewpoint.
        for (int i = 0; i < mSummary.getRowsCount(); ++i) {
          SummaryRow row = mSummary.getRows(i);
          if (row.getIdentifier() == key.getIdentifier()) {
            Log.i(TAG, "found requested viewpoint with timestamp mismatch (" +
                  key.getDayTimestamp() + " != " + row.getDayTimestamp() + "): " +
                  row.toString());
            return i;
          }
        }
      }
      return index;
    }

    // Returns the summary row structure for the specified row index.
    public SummaryRow getSummaryRow(int rowIndex) {
      if (mSummary == null) {
        return null;
      }
      if (rowIndex < 0 || rowIndex >= getRowCount()) {
        Log.i(TAG, "requested row index out of bounds " +
              rowIndex + " from 0-" + getRowCount());
        return null;
      }
      return mSummary.getRows(rowIndex);
    }

    // Returns the summary row "key" for the specified viewpoint id. The only
    // fields that will be set in this structure are SummaryRow.day_timestamp
    // and SummaryRow.identifier.
    private SummaryRow getSummaryRowKey(long viewpointId) {
      byte[] bytes = DayTable.LoadViewpointTimestampAndIdentifier(
          mDB.nativeHandle(), viewpointId);
      try {
        return SummaryRow.parseFrom(bytes);
      } catch (InvalidProtocolBufferException e) {
        return null;
      }
    }
  }

  public static final class Snapshot {
    private final DayTable mDayTable;
    private final DB mDBSnapshot;
    private final int mEpoch;
    private final ConversationSummary mConversations;

    private Snapshot(DayTable dayTable, int epoch) {
      mDayTable = dayTable;
      mDBSnapshot = mDayTable.mAppState.db().newSnapshot();
      mEpoch = epoch;
      mConversations = new ConversationSummary(mDBSnapshot);
    }

    public void release() {
      mDBSnapshot.release();
    }

    public ConversationSummary getConversations() {
      return mConversations;
    }

    public DB getDB() {
      return mDBSnapshot;
    }

    // The snapshot epoch. The epoch increases each time a new snapshot is
    // created. If the epoch has not changed, the snapshot has not changed.
    public int epoch() {
      return mEpoch;
    }

    public ActivityTable.Handle loadActivity(long activityId) {
      return mDayTable.mAppState.activityTable().loadActivity(activityId, mDBSnapshot);
    }

    public EpisodeTable.Handle loadEpisode(long episodeId) {
      return mDayTable.mAppState.episodeTable().loadEpisode(episodeId, mDBSnapshot);
    }

    public PhotoTable.Handle loadPhoto(long photoId) {
      return mDayTable.mAppState.photoTable().loadPhoto(photoId, mDBSnapshot);
    }

    public ViewpointTable.Handle loadViewpoint(long viewpointId) {
      return mDayTable.mAppState.viewpointTable().loadViewpoint(viewpointId, mDBSnapshot);
    }

    public ViewpointSummaryMetadata loadViewpointSummary(long viewpointId) {
      byte[] bytes = DayTable.LoadViewpointSummary(
          mDayTable.mNativePointer, mDBSnapshot.nativeHandle(), viewpointId);
      if (bytes == null) {
        return null;
      }
      try {
        return ViewpointSummaryMetadata.parseFrom(bytes);
      } catch (InvalidProtocolBufferException e) {
        return null;
      }
    }
  }

  private final AppState mAppState;
  private final long mNativePointer;
  private final HashSet<Runnable> mRefreshCallbacks = new HashSet<Runnable>();
  private Snapshot mSnapshot = null;
  private int mEpoch = 0;

  DayTable(AppState appState, long nativePointer) {
    mAppState = appState;
    mNativePointer = nativePointer;
  }

  public void notifyNewSnapshot() {
    Log.i(TAG, "Received notification of new snapshot.");
    HashSet<Runnable> callbacks;
    synchronized (this) {
      mSnapshot = new Snapshot(this, ++mEpoch);
      callbacks = (HashSet<Runnable>)mRefreshCallbacks.clone();
    }
    for (Runnable r : callbacks) {
      r.run();
    }
  }

  // Returns the current DayTable snapshot. Use Snapshot.epoch() to determine
  // if the snapshot has changed.
  public synchronized Snapshot getSnapshot() {
    Assert.assertNotNull(mSnapshot);
    return mSnapshot;
  }

  // Register "callback" to be invoked whenever the day table snapshot changes.
  public synchronized void registerRefreshCallback(Runnable callback) {
    mRefreshCallbacks.add(callback);
  }

  public synchronized void unregisterRefreshCallback(Runnable callback) {
    mRefreshCallbacks.remove(callback);
  }

  private static native byte[] LoadViewpointSummary(
      long day_table, long db_handle, long viewpoint_id);
  private static native byte[] LoadViewpointTimestampAndIdentifier(
      long db_handle, long viewpoint_id);
}
