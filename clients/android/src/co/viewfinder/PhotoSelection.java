// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis
package co.viewfinder;

// A small class for holding the details of a single photo selection.
public class PhotoSelection implements Comparable<PhotoSelection> {
  private final long mPhotoId;
  private final long mEpisodeId;
  private final long mTimestamp;

  public PhotoSelection(long photoId, long episodeId) {
    this(photoId, episodeId, Time.currentTimeMs());
  }

  public PhotoSelection(long photoId, long episodeId, long timestampMs) {
    mPhotoId = photoId;
    mEpisodeId = episodeId;
    mTimestamp = timestampMs;
  }

  public int compareTo(PhotoSelection s) {
    // Earlier selections compare less than later selections.
    if (mTimestamp < s.mTimestamp) {
      return -1;
    }
    if (mTimestamp > s.mTimestamp) {
      return +1;
    }
    return 0;
  }

  @Override
  public boolean equals(Object obj) {
    if (!(obj instanceof PhotoSelection)) {
      return false;
    }
    PhotoSelection s = (PhotoSelection)obj;
    return mPhotoId == s.mPhotoId && mEpisodeId == s.mEpisodeId;
  }

  @Override
  public int hashCode() {
    // This is the same as PhotoSelectionHash in our C++ code. Doesn't need to
    // be the same, but it seemed like a good hash code.
    int kPrime = 31;
    int result = kPrime + (int)(mPhotoId ^ (mPhotoId >> 32));
    return result * kPrime + (int)(mEpisodeId ^ (mEpisodeId >> 32));
  }
}
