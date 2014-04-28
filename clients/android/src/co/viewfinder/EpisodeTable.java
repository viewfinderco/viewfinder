// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis
package co.viewfinder;

import co.viewfinder.proto.ContentIdsPB.EpisodeId;
import co.viewfinder.proto.EpisodeMetadataPB.EpisodeMetadata;
import co.viewfinder.proto.PhotoMetadataPB.PhotoMetadata;
import com.google.protobuf.InvalidProtocolBufferException;
import java.util.List;

public class EpisodeTable {
  public static final class Handle {
    private long mNativePointer;
    private EpisodeMetadata mProto;

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

    // Returns the episode metadata, loading it if necessary.
    public synchronized EpisodeMetadata proto() {
      if (mProto == null) {
        byte[] val = LoadProto(mNativePointer);
        if (val == null) {
          return null;
        }
        try {
          mProto = EpisodeMetadata.parseFrom(val);
        } catch (InvalidProtocolBufferException e) {
          return null;
        }
      }
      return mProto;
    }

    // Returns a formatted location.
    public String formatLocation(boolean shorten) {
      return EpisodeTable.FormatLocation(mNativePointer, shorten);
    }

    // Returns a formatted contributor. If the episode is owned by the user,
    // returns empty string. Otherwise, returns full name if "shorten" is false
    // or first name if "shorten" is true.
    public String formatContributor(boolean shorten) {
      return EpisodeTable.FormatContributor(mNativePointer, shorten);
    }
  }

  private final long mNativePointer;

  public EpisodeTable(long nativePointer) {
    mNativePointer = nativePointer;
  }

  // Retrieves the episode handle for the specified episode id.
  public Handle loadEpisode(long episodeId, DB db) {
    long h = LoadHandle(mNativePointer, episodeId, db.nativeHandle());
    if (h == 0) {
      return null;
    }
    return new Handle(h);
  }

  // Retrieves the episode handle for the specified episode id.
  public Handle loadEpisode(EpisodeId episodeId, DB db) {
    return loadEpisode(episodeId.getLocalId(), db);
  }

  // Returns the most appropriate episode for the specified photo. We prefer
  // the original episode (as listed in p.getEpisodeId()) if
  // available. Otherwise, try to locate a non-derived episode that the user
  // has access to.
  public Handle getEpisodeForPhoto(long photo_id, DB db) {
    long h = GetEpisodeForPhoto(mNativePointer, photo_id, db.nativeHandle());
    if (h == 0) {
      return null;
    }
    return new Handle(h);
  }

  // Lists the episodes the specified photo is associated with. Returns null if
  // no episodes were found.
  public List<Long> listEpisodes(long photo_id, DB db) {
    long[] episodes = ListEpisodes(mNativePointer, photo_id, db.nativeHandle());
    return Utils.longArrayToList(episodes);
  }

  private static native long LoadHandle(
      long native_ptr, long episode_id, long db_handle);
  private static native void ReleaseHandle(long native_ptr);
  private static native long GetEpisodeForPhoto(
      long native_ptr, long photo_id, long db_handle);
  private static native long[] ListEpisodes(
      long native_ptr, long photo_id, long db_handle);
  private static native byte[] LoadProto(long native_ptr);
  private static native String FormatLocation(long native_ptr, boolean shorten);
  private static native String FormatContributor(long native_ptr, boolean shorten);
}
