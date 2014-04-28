package com.hello;

public class LocalDB {
  private boolean isOpen = false;

  public static class LoadFailedException
      extends Exception { }

  public LocalDB(String path) throws LoadFailedException {
    // Only allow one of these java instances to load the db at one time.
    if (IsLoaded()) throw new LoadFailedException();
    Load(path);
    if (!IsLoaded()) throw new LoadFailedException();
    isOpen = true;
  }

  public void dispose() {
    if (isOpen)
    {
      isOpen = false;
      Unload();
    }
  }

  // Internal life cycle management entry points in jni/localdb.cpp
  private native void Load(String path);
  private native boolean IsLoaded();
  private native void Unload();

  // Add new entry points implemented in jni/localdb.cpp here.
  // Long term, this will have all the high level entry points which understand viewfinder schema and
  //   semantics.
  //
  public native void DumpValues();
  public native void SetValue(String key, String value);
  public native String GetValue(String key);
}
