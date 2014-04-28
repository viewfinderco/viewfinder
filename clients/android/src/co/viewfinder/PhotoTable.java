// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis
package co.viewfinder;

import co.viewfinder.proto.ContentIdsPB.PhotoId;
import co.viewfinder.proto.PhotoMetadataPB.PhotoMetadata;
import com.google.protobuf.InvalidProtocolBufferException;

public class PhotoTable {
  public static final class Handle {
    private long mNativePointer;
    private PhotoMetadata mProto;

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

    // Returns the photo metadata, loading it if necessary.
    public synchronized PhotoMetadata proto() {
      if (mProto == null) {
        byte[] val = LoadProto(mNativePointer);
        if (val == null) {
          return null;
        }
        try {
          mProto = PhotoMetadata.parseFrom(val);
        } catch (InvalidProtocolBufferException e) {
          return null;
        }
      }
      return mProto;
    }

    // Returns a formatted location.
    public String formatLocation(boolean shorten) {
      return PhotoTable.FormatLocation(mNativePointer, shorten);
    }
  }

  private final long mNativePointer;

  public PhotoTable(long nativePointer) {
    mNativePointer = nativePointer;
  }

  // Retrieves the photo handle for the specified photo id.
  public Handle loadPhoto(long photoId, DB db) {
    long h = LoadHandle(mNativePointer, photoId, db.nativeHandle());
    if (h == 0) {
      return null;
    }
    return new Handle(h);
  }

  // Retrieves the photo handle for the specified photo id.
  public Handle loadPhoto(PhotoId photoId, DB db) {
    return loadPhoto(photoId.getLocalId(), db);
  }

  private static native long LoadHandle(
      long native_ptr, long photo_id, long db_handle);
  private static native void ReleaseHandle(long native_ptr);
  private static native byte[] LoadProto(long native_ptr);
  private static native String FormatLocation(long native_ptr, boolean shorten);
}
