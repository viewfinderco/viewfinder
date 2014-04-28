// Copyright 2013 Viewfinder. All rights reserved.
// Author: Marc Berhault
package co.viewfinder;

public class PhotoStorage {
  private final long mNativePointer;

  public PhotoStorage(long nativePointer) {
    mNativePointer = nativePointer;
  }

  // Returns the smallest resolution image that is greater than or equal to
  // max_size. If found, the returned string contains the full path to the image, otherwise returns null.
  // photoId is the local photo id: PhotoMetadata.id().local_id().
  public String lowerBoundFullPath(long photoId, int maxSize) {
    return LowerBoundFullPath(mNativePointer, photoId, maxSize);
  }

  private static native String LowerBoundFullPath(long photoStorage, long photoId, int maxSize);
}
