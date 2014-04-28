// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis
package co.viewfinder;

public class ContentTable {
  private final long mNativePointer;

  ContentTable(long nativePointer) {
    mNativePointer = nativePointer;
  }

  protected final byte[] loadContent(long contentId, DB db) {
    return LoadContent(mNativePointer, contentId, db.nativeHandle());
  }

  protected native byte[] LoadContent(long native_ptr, long content_id, long db_handle);
}
