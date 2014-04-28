// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis
package co.viewfinder;

import co.viewfinder.proto.ActivityMetadataPB.ActivityMetadata;
import co.viewfinder.proto.ContentIdsPB.ActivityId;
import co.viewfinder.proto.DayMetadataPB.ViewpointSummaryMetadata;
import com.google.protobuf.InvalidProtocolBufferException;

public class ActivityTable {
  public static final class Handle {
    private long mNativePointer;
    private ActivityMetadata mProto;

    Handle(long nativePointer) {
      mNativePointer = nativePointer;
    }

    public void release() {
      if (mNativePointer != 0) {
        ReleaseHandle(mNativePointer);
        mNativePointer = 0;
      }
    }

    public void finalize() {
      // In case release() was not already called...
      release();
    }

    // Returns the activity metadata, loading it if necessary.
    public synchronized ActivityMetadata proto() {
      if (mProto == null) {
        byte[] val = LoadProto(mNativePointer);
        if (val == null) {
          return null;
        }
        try {
          mProto = ActivityMetadata.parseFrom(val);
        } catch (InvalidProtocolBufferException e) {
          return null;
        }
      }
      return mProto;
    }

    // Returns a formatted timestamp, relative to the current date.
    public String formatName(boolean shorten) {
      return ActivityTable.FormatName(mNativePointer, shorten);
    }

    // Returns a formatted timestamp, relative to the current date.
    public String formatTimestamp(boolean shorten) {
      return ActivityTable.FormatTimestamp(mNativePointer, shorten);
    }

    // Returns formatted version of activity content. If not NULL, uses the
    // supplied activity row to inform the formatting of the activity contents.
    // This provides conversation-dependent context, such as eliminating photos
    // from a share activity which are duplicates in the conversation.
    public String formatContent(
        ViewpointSummaryMetadata.ActivityRow activity_row, boolean shorten) {
      byte[] activity_row_bytes = null;
      if (activity_row != null) {
        activity_row_bytes = activity_row.toByteArray();
      }
      return ActivityTable.FormatContent(mNativePointer, activity_row_bytes, shorten);
    }
  }

  private final long mNativePointer;

  ActivityTable(long nativePointer) {
    mNativePointer = nativePointer;
  }

  // Retrieves the activity handle for the specified activity id.
  public Handle loadActivity(long activityId, DB db) {
    long h = LoadHandle(mNativePointer, activityId, db.nativeHandle());
    if (h == 0) {
      return null;
    }
    return new Handle(h);
  }

  // Retrieves the activity handle for the specified activity id.
  public Handle loadActivity(ActivityId activityId, DB db) {
    return loadActivity(activityId.getLocalId(), db);
  }

  private static native long LoadHandle(
      long native_ptr, long activity_id, long db_handle);
  private static native void ReleaseHandle(long native_ptr);
  private static native byte[] LoadProto(long native_ptr);
  private static native String FormatName(
      long native_ptr, boolean shorten);
  private static native String FormatTimestamp(
      long native_ptr, boolean shorten);
  private static native String FormatContent(
      long native_ptr, byte[] activity_row, boolean shorten);
}
