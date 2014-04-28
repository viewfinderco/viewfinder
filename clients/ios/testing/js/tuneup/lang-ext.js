/**
 * Extend +destination+ with +source+
 */
function extend(destination, source) {
  for (var property in source) {
    destination[property] = source[property];
  }
  return destination;
}

/**
 * Dump the properties out a String returned by the function.
 */
function dumpProperties(obj) {
  var dumpStr = "";
  for (var propName in obj) {
    if (obj.hasOwnProperty(propName)) {
      if (dumpStr !== "") {
        dumpStr += ", ";
      }
      dumpStr += (propName + "=" + obj[propName]);
    }
  }

  return dumpStr;
}

extend(Array.prototype, {
  /**
   * Applies the given function to each element in the array until a
   * match is made. Otherwise returns null.
   * */
  contains: function(f) {
    for (i = 0; i < this.length; i++) {
      if (f(this[i])) {
        return this[i];
      }
    }
    return null;
  }
});

String.prototype.trim = function() {
  return this.replace(/^\s+|\s+$/g,"");
};

String.prototype.ltrim = function() {
  return this.replace(/^\s+/,"");
};

String.prototype.rtrim = function() {
  return this.replace(/\s+$/,"");
};

