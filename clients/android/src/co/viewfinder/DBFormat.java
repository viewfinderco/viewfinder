// Copyright 2013 Viewfinder. All rights reserved.
// Author: Marc Berhault
package co.viewfinder;

class DBFormat {
  public static String userIdKey() {
    return "u/";
  }

  public static String userIdKey(long userId) {
    return userIdKey() + Long.toString(userId);
  }
}
