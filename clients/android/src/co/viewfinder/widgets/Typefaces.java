// Copyright 2013 Viewfinder. All rights reserved.
// Author: Andy Kimball
package co.viewfinder.widgets;

import android.content.Context;
import android.graphics.Typeface;

import java.util.Hashtable;

/**
 * Global cache of Typeface objects, indexed by filename in the fonts directory.
 */
public class Typefaces {

  private static final Hashtable<String, Typeface> cache = new Hashtable<String, Typeface>();

  public static Typeface get(Context context, String name) {
    synchronized (cache) {
      if (!cache.containsKey(name)) {
        Typeface typeface = Typeface.createFromAsset(context.getAssets(), String.format("fonts/%s", name));
        cache.put(name, typeface);
      }

      return cache.get(name);
    }
  }

}