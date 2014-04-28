// Copyright 2013 Viewfinder. All rights reserved.
// Author: Marc Berhault
package co.viewfinder;

import android.util.Log;
import co.viewfinder.proto.ContactMetadataPB.ContactMetadata;

class ContactManager {
  private static final String TAG = "viewfinder.ContactManager";

  private final AppState mAppState;
  private final long mNativeContactManager;

  public ContactManager(AppState appState, long nativePointer) {
    Log.d(TAG, "ContactManager()");
    mAppState = appState;
    mNativeContactManager = nativePointer;
  }

  // Returns the count of the total number of contacts.
  public int count() {
    return Count(mNativeContactManager);
  }

  // Returns the number of contacts from the given source.
  public int countContactsForSource(String source) {
    return CountContactsForSource(mNativeContactManager, source);
  }

  // Returns the number of Viewfinder contacts (with user_id set) from given source.
  public int countViewfinderContactsForSource(String source) {
    return CountViewfinderContactsForSource(mNativeContactManager, source);
  }

  public String firstName(long userId, boolean allowNickname) {
    return FirstNameFromId(mNativeContactManager, userId, allowNickname);
  }

  public String firstName(ContactMetadata contact, boolean allowNickname) {
    return FirstNameFromProto(mNativeContactManager, contact.toByteArray(), allowNickname);
  }

  public String fullName(long userId, boolean allowNickname) {
    return FullNameFromId(mNativeContactManager, userId, allowNickname);
  }

  public String fullName(ContactMetadata contact, boolean allowNickname) {
    return FullNameFromProto(mNativeContactManager, contact.toByteArray(), allowNickname);
  }

  // If "identity" has been resolved recently, copy it into *metadata and return true.
  public ContactMetadata getCachedResolvedContact(String identity) {
    return protoFromBytes(GetCachedResolvedContact(mNativeContactManager, identity));
  }

  // Returns the last successful import of this source, or 0 if none is found.
  public double getLastImportTimeForSource(String source) {
    return GetLastImportTimeForSource(mNativeContactManager, source);
  }

  // Returns a list of contacts who have been converted to registered users since
  // the last call to ResetNewUsers.
  public ContactMetadata[] getNewUsers() {
    Object[] result = GetNewUsers(mNativeContactManager);
    return objectArrayToContactMetadataArray(result);
  }

  // Lookup user by user id; uses in-memory user cache.
  public ContactMetadata lookupUser(long userId) {
    return protoFromBytes(LookupUser(mNativeContactManager, userId, 0));
  }

  public ContactMetadata lookupUser(long userId, long nativeDBHandle) {
    return protoFromBytes(LookupUser(mNativeContactManager, userId, nativeDBHandle));
  }

  // Lookup user by identity; NOT CACHED.
  public ContactMetadata lookupUserByIdentity(String identity) {
    return protoFromBytes(LookupUserByIdentity(mNativeContactManager, identity, 0));
  }

  public ContactMetadata lookupUserByIdentity(String identity, long nativeDBHandle) {
    return protoFromBytes(LookupUserByIdentity(mNativeContactManager, identity, nativeDBHandle));
  }

  // Writes the given metadata to the database, merging it with any existing data for
  // the same identity.  Should be used after a contact_resolved callback if the
  // new data needs to be saved.
  public void mergeResolvedContact(ContactMetadata contact) {
    MergeResolvedContact(mNativeContactManager, contact.toByteArray());
  }

  public void reset() {
    Reset(mNativeContactManager);
  }

  // Deletes all contacts and causes them to be re-queried from the server.
  public void resetAll() {
    ResetAll(mNativeContactManager);
  }

  // Attempt to resolve the given identity to a user.  This method is asynchronous; callers
  // should be listening on contact_resolved().
  public void resolveContact(String identity) {
    ResolveContact(mNativeContactManager, identity);
  }

  // Unconditionally queue the specified user for retrieval.
  public void queueUser(long userId) {
    QueueUser(mNativeContactManager, userId);
  }

  public String saveContact(ContactMetadata contact, boolean upload, double now) {
    return SaveContact(mNativeContactManager, contact.toByteArray(), upload, now);
  }

  public ContactMetadata[] search(String searchText, boolean allUsers) {
    Object[] result = Search(mNativeContactManager, searchText, allUsers);
    return objectArrayToContactMetadataArray(result);
  }

  public void setLastImportTimeForSource(String source, double timestamp) {
    SetLastImportTimeForSource(mNativeContactManager, source, timestamp);
  }

  // Sets the nickname for the specified user and queues an update to the network.
  public void setFriendNickname(long userId, String nickname) {
    SetFriendNickname(mNativeContactManager, userId, nickname);
  }

  // Sets the current user's name and queues an update to the network.
  // Returns false if the given name is invalid.
  public boolean setMyName(String first, String last, String name) {
    return SetMyName(mNativeContactManager, first, last, name);
  }

  // Returns the count of viewfinder contacts.
  public int viewfinderCount() {
    return ViewfinderCount(mNativeContactManager);
  }

  // Parsing helpers.
  private ContactMetadata protoFromBytes(byte[] bytes) {
    return Utils.parseProto(bytes, ContactMetadata.PARSER);
  }

  private ContactMetadata[] objectArrayToContactMetadataArray(Object[] objects) {
    if (objects == null) {
      return null;
    }
    ContactMetadata[] ret = new ContactMetadata[objects.length];
    for (int i = 0; i < objects.length; ++i) {
      ret[i] = protoFromBytes((byte[]) objects[i]);
    }
    return ret;
  }

  // Static methods from ContactManager. No native pointer needed.

  // Construct full name based on first and last. Some locales reverse the
  // combination of first/last names.
  public static native String ConstructFullName(String first, String last);

  private static native int Count(long contactManager);
  private static native int CountContactsForSource(long contactManager, String source);
  private static native int CountViewfinderContactsForSource(long contactManager, String source);
  private static native String FirstNameFromId(long contactManager, long userId, boolean allowNickname);
  private static native String FirstNameFromProto(long contactManager, byte[] contact, boolean allowNickname);
  private static native String FullNameFromId(long contactManager, long userId, boolean allowNickname);
  private static native String FullNameFromProto(long contactManager, byte[] contact, boolean allowNickname);
  private static native byte[] GetCachedResolvedContact(long contactManager, String identity);
  private static native Object[] GetNewUsers(long contactManager);
  private static native double GetLastImportTimeForSource(long contactManager, String source);
  // If dbHandle is NULL, the contact manager uses the current DB, otherwise it queries the passed-in handle.
  private static native byte[] LookupUser(long contactManager, long userId, long dbHandle);
  private static native byte[] LookupUserByIdentity(long contactManager, String identity, long dbHandle);
  private static native void MergeResolvedContact(long contactManager, byte[] contact);
  private static native void Reset(long contactManager);
  private static native void ResetAll(long contactManager);
  private static native void ResolveContact(long contactManager, String identity);
  private static native void QueueUser(long contactManager, long userId);
  private static native String SaveContact(long contactManager, byte[] contact, boolean upload, double now);
  private static native Object[] Search(long contactManager, String searchText, boolean allUsers);
  private static native void SetLastImportTimeForSource(long contactManager, String source, double timestamp);
  private static native void SetFriendNickname(long contactManager, long userId, String nickname);
  private static native boolean SetMyName(long contactManager, String first, String last, String name);
  private static native int ViewfinderCount(long contactManager);
}
