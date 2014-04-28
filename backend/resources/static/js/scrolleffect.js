// Copyright 2012 Viewfinder Inc. All Rights Reserved.

/**
 * @fileoverview efficient vertical scrolling callback.  Allows visible scrolling behavior for a very large number
 * of objects in the DOM.
 *
 * @author matt@emailscrubbed.com (Matt Tracy)
 */

(function($, _) {  
  $.scrollEffect = function ($obj) {
    this.$obj = $obj;
  };
  
  // Instance Prototype
  $.extend($.scrollEffect.prototype, {
    dataKey : '_scrollcontainer',
    
    constructor : $.scrollEffect,
  
    save : function (options) {
      _.defaults(options, {
        childClass : '.scrolleffect',
        bufferTop : 0,
        bufferBottom : 0,
        useWindow : false
      });
      
      this.options = options;
      if (!this._binding) {
        this._binding = _.bind(this.scroll, this);
        if (options.useWindow) {
          $(window).on('scroll', this._binding);
        } else {
          this.$obj.on('scroll', this._binding); 
        }
      }
      
      this.childClass = this.options.childClass;
      this.cacheScrollEffectChildren();
      this.constructor.add(this);
      this.$obj.data(this.dataKey, this);
    },
    
    scroll : function () {
      if (!this.$obj.is(':visible')) {
        return;
      }
      
      var topBound = (this.options.useWindow ? $(window) : this.$obj).scrollTop();
      var botBound = topBound + (this.options.useWindow ? $(window) : this.$obj).height();
      
      topBound -= this.options.bufferTop;
      botBound += this.options.bufferBottom;
    
      var start = _(this.$children).sortedIndex(topBound, this._top);      
      var end = _(this.$children).sortedIndex(botBound, this._top);
      
      _(this.$children.slice(start, end)).each(function (child) {
        child.$obj.trigger('scrolleffect');
      });
    },
    
    destroy : function () {
      this.constructor.remove(this);
      if (this.options.useWindow) {
        $(window).off('scroll', this._binding);
      } else {
        this.$obj.off('scroll', this._binding);
      }
      
      this.$obj.removeData(this.dataKey);
    },
    
    cacheScrollEffectChildren : function () {
      // Calculate an adjustment based on the current offset of the parent, including
      // any current scroll offset.  The goal is to calculate each child's offset
      // relative to the parent container.
      if (this.options.useWindow) {
        parentOffset = 0;
      } else {
        parentOffset = this.$obj.offset().top - this.$obj.scrollTop();
      }
      
      var rawchildren = this.$obj.find(this.options.childClass);
      this.$children = _.chain(rawchildren)
        .map(function (rc) {
          var $rc = $(rc);
          return {
            $obj : $rc,
            top : $rc.offset().top - parentOffset
          };
        })
        .sortBy(this._top)
        .value();
    },
    
    _top : function (obj) {
      if (_.isNumber(obj)) {
        return obj;
      }
      
      return obj.top;
    }
  });
  
  // Static Prototype
  $.extend($.scrollEffect, {
    dataKey : '_scrollcontainer',
    
    containers : [],
    
    scrollContainers : function () {
      _(this.containers).each(function (container) {
        container.scroll();
      });
    },
    
    recacheChildren : function () {
      _(this.containers).each(function (container) {
        container.cacheScrollEffectChildren();
      });
    },
    
    create : function ($obj) {
      var existingSe = $obj.data(this.prototype.dataKey);
      return existingSe || new $.scrollEffect($obj);
    },
    
    add : function (scrollEffect) {
      if (this.containers.indexOf(scrollEffect) === -1) {
        this.containers.push(scrollEffect);
      }
    },
    
    remove : function (scrollEffect) {
      var index = this.containers.indexOf(scrollEffect);
      if (index !== -1) this.containers.splice(index, 1);
    }
  });
  
  // Adds an object to the list of scrollEffect containers.  It is expected that each container
  // is scrollable (such as the current window, or an div with overflow:scroll), and that
  // it will contain children with the '.scrolleffect' class.
  // 
  // Whenever the object scrolls, this class will trigger a 'scrolleffect' event on any children
  // of the object with the '.scrolleffect' class which are currently in the visible portion of the
  // object.  This is done efficiently by caching the children in a list which is sorted by the offset 
  // of each child from the top of the container.
  $.fn.scrollEffect = function (option) {
    return this.each(function () {
      var $this = $(this);
      var se = $.scrollEffect.create($this);

      if (option === 'destroy') {        
        se.destroy();
      } else {
        se.save(option || {});
      }
    });
  };
  
  var recacheAndScroll = function () {
    $.scrollEffect.recacheChildren();
    $.scrollEffect.scrollContainers();
  };
  
  // During load there is a flurry of DOM modifications - a simple debounce is
  // enough to smooth it out completely.
  var debounceRaS = _.simpleDebounce(recacheAndScroll);

  $(window).on('resize', debounceRaS);
  
  //run checks when these methods are called
  $.each(['append', 'prepend', 'after', 'before', 'remove', 'show', 'hide'], function(i, n) {
    var old = $.fn[n];
    if (old) {
      $.fn[n] = function() {
        var r = old.apply(this, arguments);
        debounceRaS();
        return r;
      };
    }
  });
})(jQuery, _);
