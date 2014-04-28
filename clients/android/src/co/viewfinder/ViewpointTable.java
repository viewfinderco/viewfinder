// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis
package co.viewfinder;

import co.viewfinder.proto.ContactMetadataPB.ContactMetadata;
import co.viewfinder.proto.ContentIdsPB.ViewpointId;
import co.viewfinder.proto.ViewpointMetadataPB.ViewpointMetadata;
import com.google.protobuf.InvalidProtocolBufferException;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;

public class ViewpointTable {
  public static final class Handle {
    private long mNativePointer;
    private ViewpointMetadata mProto;

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

    // Returns the viewpoint metadata, loading it if necessary.
    public synchronized ViewpointMetadata proto() {
      if (mProto == null) {
        byte[] val = LoadProto(mNativePointer);
        if (val == null) {
          return null;
        }
        try {
          mProto = ViewpointMetadata.parseFrom(val);
        } catch (InvalidProtocolBufferException e) {
          return null;
        }
      }
      return mProto;
    }

    // Returns the viewpoint title. If none has been set explicitly, creates one
    // based on the content of the viewpoint.
    public String formatTitle(boolean shorten, boolean normalizeWhitespace) {
      return ViewpointTable.FormatTitle(mNativePointer, shorten, normalizeWhitespace);
    }

    // Returns the default title for use when no title has been explicitly
    // set for the viewpoint.
    public String defaultTitle() {
      return ViewpointTable.DefaultTitle(mNativePointer);
    }
  }

  private final long mNativePointer;

  public ViewpointTable(long nativePointer) {
    mNativePointer = nativePointer;
  }

  // Retrieves the viewpoint handle for the specified viewpoint id.
  public Handle loadViewpoint(long viewpointId, DB db) {
    long h = LoadHandle(mNativePointer, viewpointId, db.nativeHandle());
    if (h == 0) {
      return null;
    }
    return new Handle(h);
  }

  // Retrieves the viewpoint handle for the specified viewpoint id.
  public Handle loadViewpoint(ViewpointId viewpointId, DB db) {
    return loadViewpoint(viewpointId.getLocalId(), db);
  }

  // Lists the viewpoints (other than default) the specified photo has been
  // shared to.
  public List<Long> listViewpointsForPhotoId(long photoId, DB db) {
    long[] viewpoints = ListViewpointsForPhotoId(
        mNativePointer, photoId, db.nativeHandle());
    return Utils.longArrayToList(viewpoints);
  }

  // Lists the viewpoints the specified user is a follower of.
  public List<Long> listViewpointsForUserId(long userId, DB db) {
    long[] viewpoints = ListViewpointsForUserId(
        mNativePointer, userId, db.nativeHandle());
    return Utils.longArrayToList(viewpoints);
  }

  // Add followers to an existing viewpoint. Returns true if the followers were
  // successfully added and false otherwise.
  public boolean addFollowers(long viewpointId, List<ContactMetadata> contacts) {
    return AddFollowers(
        mNativePointer, viewpointId, makeContactArray(contacts));
  }

  // Commits a provisional viewpoint, allowing it to be uploaded to the server.
  public boolean commitShareNew(long viewpointId, DB db) {
    return CommitShareNew(mNativePointer, viewpointId, db.nativeHandle());
  }

  // Posts a comment to an existing viewpoint. If "replyToPhotoId" is not 0,
  // sets the "asset_id" in the post metadata to the server id of the photo in
  // question. Returns true if the comment was successfully posted and false
  // otherwise.
  public boolean postComment(
      long viewpointId, String message, long replyToPhotoId) {
    return PostComment(mNativePointer, viewpointId, message, replyToPhotoId);
  }

  // Remove followers from an existing viewpoint. Returns true if the followers
  // were successfully removed and false otherwise.
  public boolean removeFollowers(long viewpointId, HashSet<Long> userIds) {
    long[] a = new long[userIds.size()];
    int i = 0;
    for (Long v : userIds) {
      a[i++] = v;
    }
    return RemoveFollowers(mNativePointer, viewpointId, a);
  }

  // Removes the viewpoint from the inbox view if label_removed has not been
  // set. This invokes /service/remove_viewpoint on the server. Returns true if
  // the viewpoint was successfully removed and false otherwise.
  public boolean removeViewpoint(long viewpointId) {
    return RemoveViewpoint(mNativePointer, viewpointId);
  }

  // Shares photos to a new viewpoint. Returns null on failure and the new
  // viewpoint on success. If "provisional" is true, the new viewpoint will not
  // be uploaded to the server until the provisional bit is cleared.
  public Handle shareNew(
      HashSet<PhotoSelection> photoIds, List<ContactMetadata> contacts,
      String title, boolean provisional) {
    long h = ShareNew(
        mNativePointer, makeSortedPhotoSelection(photoIds),
        makeContactArray(contacts), title, provisional);
    if (h == 0) {
      return null;
    }
    return new Handle(h);
  }

  // Shares photos to an existing viewpoint. Returns null on failure and the
  // viewpoint on success. If "updateCoverPhoto" is specified, the cover photo
  // will be modified to the first photo in the photoIds selection.
  public Handle shareExisting(
      long viewpointId, HashSet<PhotoSelection> photoIds, boolean updateCoverPhoto) {
    long h = ShareExisting(
        mNativePointer, viewpointId,
        makeSortedPhotoSelection(photoIds), updateCoverPhoto);
    if (h == 0) {
      return null;
    }
    return new Handle(h);
  }

  // Unshares photos from an existing viewpoint. Returns null on failure and
  // the viewpoint on success. Returns true if the photos were successfully
  // unshared and false otherwise.
  public boolean unshare(long viewpointId, HashSet<PhotoSelection> photoIds) {
    return Unshare(mNativePointer, viewpointId,
                   makeSortedPhotoSelection(photoIds));
  }

  // Updates the viewpoint cover photo. Returns true if the cover photo was
  // successfully updated and false otherwise.
  public boolean updateCoverPhoto(long viewpointId, long photoId, long episodeId) {
    return UpdateCoverPhoto(mNativePointer, viewpointId, photoId, episodeId);
  }

  // Update an existing share new activity. Returns false if the activity could
  // not be updated (e.g it is not provisional or does not exist) and true if
  // the activity was updated. Note that any existing photos in the share new
  // activity are replaced with the photos specified in the photo_ids vector.
  // The activity's timestamp is updated to the current time.
  public boolean updateShareNew(
      long viewpointId, long activityId, HashSet<PhotoSelection> photoIds) {
    return UpdateShareNew(mNativePointer, viewpointId, activityId,
                          makeSortedPhotoSelection(photoIds));
  }

  // Updates the viewpoint title. Returns true if the title was successfully
  // updated and false otherwise.
  public boolean updateTitle(long viewpointId, String title) {
    return UpdateTitle(mNativePointer, viewpointId, title);
  }

  // Updates the viewpoint "viewed_seq" property on the server to mark the
  // viewpoint as viewed. Returns true if the "viewed_seq" number was
  // successfully updated and false otherwise.
  public boolean updateViewedSeq(long viewpointId) {
    return UpdateViewedSeq(mNativePointer, viewpointId);
  }

  // Update the viewpoint autosave label. Returns if the autosave label was
  // successfully updated and false otherwise.
  public boolean updateAutosaveLabel(long viewpointId, boolean autosave) {
    return UpdateAutosaveLabel(mNativePointer, viewpointId, autosave);
  }

  // Update the viewpoint hidden label. Returns if the hidden label was
  // successfully updated and false otherwise.
  public boolean updateHiddenLabel(long viewpointId, boolean hidden) {
    return UpdateHiddenLabel(mNativePointer, viewpointId, hidden);
  }

  // Update the viewpoint muted label. Returns if the muted label was
  // successfully updated and false otherwise.
  public boolean updateMutedLabel(long viewpointId, boolean muted) {
    return UpdateMutedLabel(mNativePointer, viewpointId, muted);
  }

  private Object[] makeSortedPhotoSelection(HashSet<PhotoSelection> photoIds) {
    Object[] a = photoIds.toArray();
    Arrays.sort(a);
    return a;
  }

  private Object[] makeContactArray(List<ContactMetadata> contacts) {
    byte[][] a = new byte[contacts.size()][];
    int i = 0;
    for (ContactMetadata c : contacts) {
      a[i++] = c.toByteArray();
    }
    // Note that a java array (e.g. byte[]) is an Object.
    return a;
  }

  // Handle loading methods.
  private static native long LoadHandle(
      long native_ptr, long episode_id, long db_handle);
  private static native void ReleaseHandle(long native_ptr);
  private static native byte[] LoadProto(long native_ptr);

  // Handle native methods.
  private static native String DefaultTitle(long native_ptr);
  private static native String FormatTitle(
      long native_ptr, boolean shorten, boolean normalize_whitespace);

  // ViewpointTable native methods.
  private static native boolean AddFollowers(
      long native_ptr, long viewpoint_id, Object[] contacts);
  private static native boolean CommitShareNew(
      long native_ptr, long viewpoint_id, long db_handle);
  private static native long[] ListViewpointsForPhotoId(
      long native_ptr, long photo_id, long db_handle);
  private static native long[] ListViewpointsForUserId(
      long native_ptr, long user_id, long db_handle);
  private static native boolean PostComment(
      long native_ptr, long viewpoint_id, String message,
      long reply_to_photo_id);
  private static native boolean RemoveFollowers(
      long native_ptr, long viewpoint_id, long[] user_ids);
  private static native boolean RemoveViewpoint(
      long native_ptr, long viewpoint_id);
  private static native long ShareNew(
      long native_ptr, Object[] photo_ids,
      Object[] contacts, String title, boolean provisional);
  private static native long ShareExisting(
      long native_ptr, long viewpoint_id,
      Object[] photo_ids, boolean update_cover_photo);
  private static native boolean Unshare(
      long native_ptr, long viewpoint_id, Object[] photo_ids);
  private static native boolean UpdateCoverPhoto(
      long native_ptr, long viewpoint_id, long photo_id, long episode_id);
  private static native boolean UpdateShareNew(
      long native_ptr, long viewpoint_id, long activity_id,
      Object[] photo_ids);
  private static native boolean UpdateTitle(
      long native_ptr, long viewpoint_id, String title);
  private static native boolean UpdateViewedSeq(
      long native_ptr, long viewpoint_id);
  private static native boolean UpdateAutosaveLabel(
      long native_ptr, long viewpoint_id, boolean autosave);
  private static native boolean UpdateHiddenLabel(
      long native_ptr, long viewpoint_id, boolean hidden);
  private static native boolean UpdateMutedLabel(
      long native_ptr, long viewpoint_id, boolean muted);
}
