// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import java.text.DateFormat;
import java.text.SimpleDateFormat;
import java.text.DateFormatSymbols;
import java.util.Calendar;
import java.util.Date;

/**
 *  Collection of time related utilities.
 *  It doesn't completely capture the formatting that's being done in the iOS client, but is good enough for now.
 */
public class Time {
  public static final long MS_PER_SECOND = 1000;
  public static final long SECONDS_PER_MINUTE = 60;
  public static final long MINUTES_PER_HOUR = 60;
  public static final long HOURS_PER_DAY = 24;
  public static final long MAX_DAYS_AGO = 7;
  public static final long MS_PER_HOUR = MS_PER_SECOND * SECONDS_PER_MINUTE * MINUTES_PER_HOUR;

  public enum TimeFormat {
    TIME_FORMAT_SHORT,  // e.g. "42m"
    TIME_FORMAT_MEDIUM,  //  e.g. "42m ago"
    TIME_FORMAT_LONG,  // e.g. "42 minutes ago"
  }

  public static long currentTimeMs() {
    return System.currentTimeMillis();
  }

  public static long currentTime() {
    return currentTimeMs() / 1000;
  }

  public static long secondsSince(long timestamp) {
    return (currentTime() - timestamp);
  }

  public static String formatTime(long timeMS, long nowMS) {
    // Switch to explicit date formats.
    Calendar calendarAgo = Calendar.getInstance();
    Calendar calendarNow = Calendar.getInstance();
    calendarAgo.setTimeInMillis(timeMS);
    calendarNow.setTimeInMillis(nowMS);
    DateFormat df;
    if (calendarAgo.get(Calendar.YEAR) != calendarNow.get(Calendar.YEAR)) {
      df = new SimpleDateFormat("MMM d, yyyy");
    } else {
      df = new SimpleDateFormat("MMM d");
    }
    return  df.format(new Date(timeMS));
  }

  public static String formatTime(long timeMS) {
    return formatTime(timeMS, System.currentTimeMillis());
  }

  public static String formatRelativeTime(long timeMS, long nowMS, TimeFormat format) {
    long elapsedS = (nowMS - timeMS) / MS_PER_SECOND;
    if (elapsedS <= 1) {
      return (format == TimeFormat.TIME_FORMAT_SHORT) ? "now" : "just now";
    }
    if (elapsedS < SECONDS_PER_MINUTE) {
      return formatTimeAgoString(format, elapsedS, "s", "seconds");
    }
    long elapsedM = elapsedS / SECONDS_PER_MINUTE;
    if (1 == elapsedM) {
      return formatTimeAgoString(format, elapsedM, "m", "minute");
    } else if (elapsedM < MINUTES_PER_HOUR) {
      return formatTimeAgoString(format, elapsedM, "m", "minutes");
    }
    long elapsedH = elapsedM / MINUTES_PER_HOUR;
    if (1 == elapsedH) {
      return formatTimeAgoString(format, elapsedH, "h", "hour");
    } else if (elapsedH < HOURS_PER_DAY) {
      return formatTimeAgoString(format, elapsedH, "h", "hours");
    }
    long elapsedDays = elapsedH / HOURS_PER_DAY;
    if (1 == elapsedDays) {
      return formatTimeAgoString(format, elapsedDays, "d", "day");
    } else if (elapsedDays < MAX_DAYS_AGO) {
      return formatTimeAgoString(format, elapsedDays, "d", "days");
    }
    // Switch to explicit date formats.
    Calendar calendarAgo = Calendar.getInstance();
    Calendar calendarNow = Calendar.getInstance();
    calendarAgo.setTimeInMillis(timeMS);
    calendarNow.setTimeInMillis(nowMS);
    DateFormat df;
    if (calendarAgo.get(Calendar.YEAR) != calendarNow.get(Calendar.YEAR)) {
      df = new SimpleDateFormat("MMM d, yyyy");
    } else {
      df = new SimpleDateFormat("MMM d");
    }
    return (TimeFormat.TIME_FORMAT_SHORT == format ? "" : "on ") + df.format(new Date(timeMS));
  }

  public static String formatRelativeTime(long timeMS, TimeFormat format) {
    return formatRelativeTime(timeMS, System.currentTimeMillis(), format);
  }

  public static String formatExactTime(long timeMS) {
    SimpleDateFormat sdf = new SimpleDateFormat("h:mma, EEEE, MMMM d, yyyy");

    // Viewfinder time formatting uses a simple 'a' or 'p' to denote AM vs. PM.
    DateFormatSymbols symbols = sdf.getDateFormatSymbols();
    symbols.setAmPmStrings(new String[] {"a", "p"});
    sdf.setDateFormatSymbols(symbols);

    return sdf.format(new Date(timeMS));
  }

  private static String formatTimeAgoString(TimeFormat format, long timeAgo, String abbrev, String word) {
    if (format == TimeFormat.TIME_FORMAT_SHORT) {
      return String.format("%d%s", timeAgo, abbrev);
    } else if (format == TimeFormat.TIME_FORMAT_MEDIUM) {
      return String.format("%d%s ago", timeAgo, abbrev);
    }
    return String.format("%d %s ago", timeAgo, word);
  }
}
