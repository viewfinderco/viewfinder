// Copyright 2012 Viewfinder Inc. All Rights Reserved.

/**
 * @fileoverview Model structures for Viewfinder website.
 *
 * @author matt@emailscrubbed.com (Matt Tracy)
 */

/** @namespace */
viewfinder.views = {};

(function($, namespace) {
  "use strict";
  
  // **********************************************************************************************
  //                                   ABSTRACT VIEWS
  // **********************************************************************************************
  
  var LayoutAndEventManager = Backbone.Model.extend({
    initialize : function() {
      var $w = $(window);
      $w.resize(_.bind(this.onResizeWindow, this));
      $w.scroll(_.bind(this.onScrollWindow, this));
      $(document).keydown(_.bind(this.onKeydownDocument, this));

      this.selectLayout();
    },

    onResizeWindow : function () {
      this.trigger('resize', $(window));
      this.selectLayout();
    },

    onScrollWindow : function () {
      this.trigger('scroll', $(window));
    },

    onKeydownDocument : function (e) {
      this.trigger('keydown', e);
    },

    layout : function () {
      return this.get('layout');
    },

    minorLayout : function () {
      return this.get('minorLayout');
    },

    selectLayout : function () {
      var w = $(window).width();
      if (w < 500) {
        this.set({
          layout : 'Mobile',
          minorLayout : 'thin'
        });
      } else if (w < 800) { 
        this.set({
          layout : 'OneCol',
          minorLayout : w < 670 ? 'thin' : 'wide'
        });
      } else {
        this.set({
          layout : 'TwoCol',
          minorLayout : w < 1080 ? 'thin' : 'wide'
        });       
      }
    }
  });

  var layoutManager = new LayoutAndEventManager();

  /**
   * Base class for Viewfinder views.  Provides a model for properly creating and destroying nested
   * views, ensuring that all bindings to the model are unbound upon destruction.
   * 
   * @class
   */
  var ViewfinderView = Backbone.View.extend({
    /**
     * Destroys this view, including all nested views.
     * 
     * @function
     * @param {Boolean} parentDestroyed If true, this view's parent is also being destroyed.  In this
     * case, only events need to be unbound - the DOM cleanup will be handled by the parent.
     */
    destroy : function (parentDestroyed) {
      parentDestroyed = parentDestroyed || false;
      
      // Destroy children first.
      this.destroyChildren(true);

      // Call OnDestroy method if it exists.
      if (this.onDestroy) {
        this.onDestroy();
      }

      // Unbind all window bindings.
      for (var e in this._domEvents) {
        var info = e.split('$');
        $(window[info[0]]).off(info[1], this._domEvents[e]);
        delete this._domEvents[e];
      }
      
      // Unbind all events attached to this view.
      this.off();

      if (!parentDestroyed) {
        // Remove this view from the DOM.
        this.remove();
      } else {
        this.stopListening();
      }
    },
    
    /**
     * Destroys only the children of this view.
     * 
     * @function
     * @param {Boolean} parentDestroyed If true, the parent view is also being destroyed.  In this
     * case, only events need to be unbound - the DOM cleanup will be handled by the parent.  
     */
    destroyChildren : function (parentDestroyed) {
      parentDestroyed = parentDestroyed || false;
      
      // Trigger destroy event.  Children will be hooked up to this if they are created with the 
      // 'create' function of a ViewfinderView.
      this.trigger('destroy', parentDestroyed);
    },
    
    /**
     * Binds the given callback function to this view's model for the given events.  This view will
     * be used as the context for the callback.
     *  
     * @function
     * @param {String} events
     * @param {Function} callback
     */
    bindModel : function (events, callback) {
      this.listenTo(this.model, events, callback);
    },
    
     /**
     * Binds the given callback function to this view's collection for the given events.  This view will
     * be used as the context for the callback.
     *  
     * @function
     * @param {String} events
     * @param {Function} callback
     */
    bindCollection : function (events, callback) {
      this.listenTo(this.collection, events, callback);
    },
    
    /**
     * Binds the given callback to the windows resize function - the callback will be removed whenever
     * this view is destroyed.  The callback is automatically bound to this view.
     * 
     * @param {Function} callback Function to be called when the window resizes.  If no function is specified, removes
     * any current resize binding for this view.
     */
    bindResize : function (callback) {
      this.stopListening(layoutManager, 'resize');
      if (callback) {
        this.listenTo(layoutManager, 'resize', callback); 
      }
    },
    
    /**
     * Binds the given callback to the windows scroll function - the callback will be removed whenever
     * this view is destroyed.  The callback is automatically bound to this view.
     * 
     * @param {Function} callback Function to be called when the window scrolls.  If no function is specified, removes
     * any current scroll binding for this view.
     */
    bindScroll : function (callback) {
      this.stopListening(layoutManager, 'scroll');
      if (callback) {
        this.listenTo(layoutManager, 'scroll', callback);
      }
    },

    /**
     * Binds the given callback to the documents keydown function - the callback will be removed whenever
     * this view is destroyed.  The callback is automatically bound to this view.
     * 
     * @param {Function} callback Function to be called when a key is pressed at the document level.
     *  If no function is specified, removes any current scroll binding for this view.
     */
    bindKeydown : function (callback) {
      this.stopListening(layoutManager, 'keydown');
      if (callback) {
        this.listenTo(layoutManager, 'keydown', callback);
      }
    },

    bindLayoutChange : function (callback) {
      this.stopListening(layoutManager, 'change:layout');
      if (callback) {
        this.listenTo(layoutManager, 'change:layout', callback);
      }
    },

    bindMinorLayoutChange : function (callback) {
      this.stopListening(layoutManager, 'change:minorLayout');
      if (callback) {
        this.listenTo(layoutManager, 'change:minorLayout', callback);
      }
    },
    
    /**
     * Binds the given callback to the given event on a DOM element - the callback will be removed whenever
     * this view is destroyed.  The callback is automatically bound to this view.
     * 
     * @param {Function} callback Function to be called when the given event triggers on the DOM element.  
     * If no function is specified, removes any current event binding for this view.
     */
    bindDom : function (elementName, eventName, callback) {
      var events, e, $e, uniqueName;
      this._domEvents = this._domEvents || {};
      events = this._domEvents;
      e = window[elementName];
      $e = $(e);
      uniqueName = elementName + '$' + eventName;
      
      if (events[uniqueName]) {
        $e.off(eventName, events[uniqueName]);
        delete events[uniqueName];
      }
      
      if (callback) {
        events[uniqueName] = _.bind(callback, this);
        $e.on(eventName, events[uniqueName]);
      }
    },
    
    /**
     * Retrieve a template function for this view, if it exists.  A view may have multiple
     * templates, which can be specified by the 'templateName' parameter.  If templateName
     * is not specified, this function instead will use either the 'templateName' member
     * of the view, or 'className' if 'templateName' is not available.
     * 
     * @function
     * @param {String} templateName the name of the template to return.
     */
    template : function (templateName) {
      templateName = templateName || this.templateName || this.className;
      if (!templateName) return null;

      var memberName = '_template' + templateName;

      if (_.isUndefined(this.constructor.prototype[memberName])) {
        this.constructor.prototype[memberName] = _.template($('#t-' + templateName).html());
      }
      
      return this[memberName];
    },
    
    /**
     * Creates a new child view and appends its DOM element as a child of this view's DOM
     * 
     * @function
     * @param {Function} constructor
     * @param {Object} options
     */
    appendChild : function (constructor, options) {
      var newView = constructor.create(options, this);
      this.$el.append(newView.$el);
      return newView.render();
    },
    
    /**
     * Creates a new child view and assigns it a DOM element which is already a child of this
     * view's DOM element.
     * 
     * @function
     * @param {String} selector
     * @param {Function} constructor
     * @param {Object} options
     */
    assignChild : function (selector, constructor, options) {
      var newView = constructor.create(options, this);   
      return newView.setElement(this.$(selector)).render();
    },
    
    /**
     * Insert a sub view at the correct index among a number of siblings.
     * 
     * @function
     * @param {Function} constructor Constructor of the view to be inserted.
     * @param {Object} options Options used to create the new sibling view.
     * @param {Integer} index the index of the view among its siblings.
     * @param {string} siblingclass a CSS class which identifies siblings of the view.
     */
    insertChild : function (constructor, options, index) {
      var view = this;
      var $view = this.$el;
      var siblingClass = '.' + constructor.prototype.className;
      var newView = constructor.create(options, view);  
      
      if (index === 0) {
        $view.prepend(newView.el);
      } else {
        var $sibs = view.$(siblingClass);
        if (index === $sibs.length) {
          $view.append(newView.el);
        } else {
          $sibs.eq(index).before(newView.el);
        }
      }
      
      return newView.render();
    },
    
    
    /**
     * Cause the view to fade into view.  This will only work if the user's browser supports
     * CSS 3 transitions - in older browsers, the element will simply appear.
     * 
     * @function
     */
    fadeIn : function () {
      var $t = this.$el;
      if (!viewfinder.fx.animation) {
        // Fade effects can overwhelm mobile site. 
        return;
      }
      
      $t.css('opacity', 0);
      _.defer(function () {
        $t.addClass('fade');
        $t.css('opacity', 1);
      });
    }
  },{
    
    /**
     * Class method - creates a new instance of the class.  If a parent view is given, then the 
     * destroy() method of the new view will be bound to the 'destroy' event of the parent.
     * 
     * @function
     * @param {Object} options
     * @param {ViewfinderView} parentView
     */
    create : function (options, parentView) {
      var newView = new this(options);
      if (parentView) {
        newView.listenTo(parentView, 'destroy', newView.destroy);
      }
      
      return newView;
    }
  });


  // View with the primary responsibility of rendering a collection of objects by
  // assigning each object in the collection to a child view.
  var CollectionView = ViewfinderView.extend({
    renderCollection : function (collection, childViewType, viewMapCallback) {
      if (!this._childViews) {
        this._childViews = {};
      }

      // Get the current list of child DOM elements.
      var newViews = {};
      for (var i = 0; i < collection.length; i++) {
        // Retrieve or create the child view for an element.
        var model = collection instanceof Backbone.Collection ? collection.at(i) : collection[i];
        var view = this._childViews[model.id];
        var isNewView = false;
        if (!view) { 
          isNewView = true;
          view = childViewType.create({model : model} , this);
        }
        
        this.$el.append(view.el);
        newViews[model.id] = view;
        this._childViews[model.id] = null;

        if (isNewView) {
          view.render();
        }

        if (viewMapCallback) {
          viewMapCallback(view, i);
        }
      }

      // Remove deleted elements, which were not touched by the collection.
      _(this._childViews).chain().values()
        .each(function (view) {
          if (view !== null) {
            view.destroy();
          }
        });
      
      this._childViews = newViews;
    }
  });
  
  var SimpleTemplateView = ViewfinderView.extend({
    render : function () {
      this.$el.html(this.template()());
      return this;
    }
  });
  
  // **********************************************************************************************
  //                                   TEXT VIEWS
  // **********************************************************************************************
  var TimestampView = ViewfinderView.extend({
    tagName : 'span',
    
    className : 'timestamp',
    
    initialize : function () {
      this.timestamp = this.options.timestamp;
      this.format = this.options.format || 'full';
    },
    
    render : function () {
      if (this.format === 'both') {
        // 'both' option should be used if the display length will be selected using css.
        var fulltext = this.getDateText('full');
        var shorttext = this.getDateText('short');
        this.$el.html('<span class="full">' + fulltext + '</span><span class="short">' + shorttext + '</span>');
      } else {
        this.$el.text(this.getDateText(this.format));
      }
      
      return this;
    },
    
    getDateText : function (size) {
      var dateFormat = 'dddd, mmmm d yyyy';
      
      if (size === 'full') {
        return this.timestamp.format('dddd, mmmm d yyyy');
      } else {
        return viewfinder.util.shortTimeString(this.timestamp);
      }
    }
  });

  // **********************************************************************************************
  //                                   FORM VIEWS
  // **********************************************************************************************

  // Template used for individual form fields rendered by backbone-forms. 
  var FormFieldTemplate = _.template('<div class="form-field" data-editor></div>');
  var CheckboxTemplate = _.template('<span class="right"><span data-editor></span>'
                                    + '<span class="label"><%= title %></span></span>');
  
  // View for displaying generic errors from a model used by backbone-forms.
  var DialogErrorsView = ViewfinderView.extend({
    initialize : function () {
      this.bindModel('change:errors', this.render);  
    },
    
    render : function () {
      var $view = this.$el;
      $view.empty();
      var errors = this.model.get('errors');
      if (!errors) {
        return;
      }
      
      if (_.isObject(errors)) {
        _(errors).each(function (val, key) {
          if (key === '_others') {
            return;
          }
          
          if (_.isObject(val)) {
            val = val.message;
          }
          
          $view.append('<span class="error">' + val + '</span>');
        });
      } else {
        $view.append('<span class="error">' + errors + '</span>');
      }
    }
  });

  // Base view for all dialog views.  A dialog features a primary submit button, with potential 
  // 'sub' and 'super' options (displayed below and above the main form).
  var DialogBaseView = ViewfinderView.extend ({
    events : {
      'click .submit' : 'onSubmit',
      'click .suboption a' : 'subOption',
      'click .cancel' : 'onCancel'
    },
    
    render : function () {
      this.destroyChildren();
      if (this.$('.errors').length > 0) {
        this.assignChild('.errors', DialogErrorsView, { model : this.model });
      }
      
      return this;
    },
    
    onSubmit : function (e) {
      this.model.proceed();
      e.stopPropagation();
    },
    
    subOption : function (e) {
      // Do nothing by default.
      e.stopPropagation();
    },
    
    onCancel : function (e) {
      // Do nothing by default.
      e.stopPropagation();
    }       
  });
  
  // Base view for dialog which displays an input form.
  var FormDialogBaseView = DialogBaseView.extend ({
    events : {
      'click .submit' : 'onSubmit',
      'click .suboption a' : 'subOption',
      'click .cancel' : 'onCancel',
      'keypress input[type=text]' : 'filterEnter',
      'keypress input[type=password]' : 'filterEnter',
      'keypress textarea' : 'filterEnter'
    },

    initialize : function () {
      this.form = new Backbone.Form({
        schema : this.formSchema,
        template : this.template(),
        model : this.model
      });
      
      var view = this;
      this.form.templateData = function () {
        // Pipe template data from child view.
        return _.result(view, 'templateData');
      };
    },
    
    render : function () {
      this.destroyChildren();
      this.$el.append(this.form.render().el);
      this.assignChild('.errors', DialogErrorsView, { model : this.model });
      this.$('input').placeholder();
      this.$('textarea').placeholder();
      return this;
    },

    filterEnter : function (e) {
      if (e.keyCode === 13 && !e.shiftKey) {
        this.onSubmit();
        e.preventDefault();
      }
    },
    
    onSubmit : function () {
      var errors = this.form.commit({ validate : true });
      if (!errors) {
        this.model.proceed();
      } else {
        this.model.set('errors', errors);
      }
    }
  });

  // **********************************************************************************************
  //                                   EFFECTS
  // ********************************************************************************************** 
  function grayscaleEffect(image) {
    // Create a new canvas off-screen.
    var canvas = document.createElement('canvas');
    canvas.width = image.width;
    canvas.height = image.height; 

    // Draw the image to the canvas.
    var ctx = canvas.getContext('2d');
    ctx.drawImage(image, 0, 0); 

    // Apply simple grayscale effect to the image's pixels - average of all channels.
    var imgPixels = ctx.getImageData(0, 0, canvas.width, canvas.height);
    for(var y = 0; y < imgPixels.height; y++){
      for(var x = 0; x < imgPixels.width; x++){
        var i = (y * 4) * imgPixels.width + x * 4;
        var avg = (imgPixels.data[i] + imgPixels.data[i + 1] + imgPixels.data[i + 2]) / 3;
        imgPixels.data[i] = avg; 
        imgPixels.data[i + 1] = avg; 
        imgPixels.data[i + 2] = avg;
      }
    }

    // Apply the grayscale effect back to the canvas.
    ctx.putImageData(imgPixels, 0, 0, 0, 0, imgPixels.width, imgPixels.height);

    // return a new image object with the Canvas data as the source.
    var newImage = new Image();
    newImage.src = canvas.toDataURL();
    return newImage;
  }
  
  
  // **********************************************************************************************
  //                                   PHOTO VIEW
  // **********************************************************************************************
  
  // Variable containing the current image size for photos.  Adjusted based on the width of the screen.
  var photoImageSize = 'full';
  
  // View which contains a single photograph.
  var PhotoView = namespace.PhotoView = ViewfinderView.extend({
    className : 'photo',
    
    initialize : function (options) {
      this.scrollLoad = options.scrollLoad || false;
      this.dynamicResize = options.dynamicResize || false;
      this.containerAspect = options.containerAspect || null;
      this.border = options.border || false;
      this.size = options.size || this.selectSize();
      this.canvasEffect = options.canvasEffect;
    },
    
    render : function () {
      var view = this;
      var $view = this.$el;
      var photo = this.model;
      
      $view.empty();
      
      // Because activities load before photos, we occasionally put a placeholder photo into the model
      // with the intention that real data will be loaded for that photo later.  If we encounter
      // such a photo in the view, we just display nothing. 
      if (photo.isPlaceholder()) {
        $view.addClass('loading');
        view.listenToOnce(photo, 'change', this.render);
        view.needsTransition = true;
        return this;
      }
      
      var image = photo.cached(view.size);
      if (image) {
        // Image is either cached, or has already been determined to be missing.
        $view.removeClass('loading scrolleffect');
        $view.off('scrolleffect');
        
        if (image === photo.MISSING_IMAGE) {
          $view.addClass('missing');
        } else {
          if (view.canvasEffect) {
            image = view.canvasEffect(image);
          }

          if (view.dynamicResize) {
            view.bindResize(function () {
              view.renderImage(image);
              view.renderEffect(image);
            });
          }
          
          view.renderImage(image);
          view.renderEffect(image);
        }
      } else {
        // No view has attempted to load this photo yet.
        view.bindModel('change:cached_' + view.size, view.render);
        $view.addClass('loading');
        
        // Disable per-image transitions if animations are disabled.
        view.needsTransition = viewfinder.fx.animation;
        
        if (view.scrollLoad) {
          $view.addClass('scrolleffect');
          $view.on('scrolleffect', function () {
            photo.loadImage(view.size);
            $view.off('scrolleffect');
          });
        } else {
          photo.loadImage(view.size);
        }
      }
      
      // Blank div for applying border effects.  Needed because css borders
      // don't play nice with our percentage-based image aspect calculations.
      if (this.border) {
        this.$el.append('<div class="border"></div>');
      }
      
      return this;
    },
    
    renderImage : function (image) {
      this.$el.append(image);
    },
    
    renderEffect : function (image) {
      if (this.needsTransition) {
        this.needsTransition = false;
        var $img = $(image);
        $img.css('opacity', 0);
        _.defer(function () {
          $img.addClass('fade');
          $img.css('opacity', 1);
        });
      }
    },
    
    // Selects the size of image to load for this container - can be overridden in child classes.
    selectSize : function () {
      return photoImageSize;
    }
  });
  
  // Display a photo image in such a way that the element containing the image is 'filled'.
  // The aspect ratio of the image will be preserved, but the image will be resized and cropped
  // such that it completely fills its container (the container is sized using CSS).  
  //
  // Images cropped horizontally will be centered; images cropped vertically will be centered
  // on the top third of the image.  This is based on common experience that the focus of portrait
  // images is most often located in the top third of the image.
  var CroppedPhotoView = namespace.CroppedPhotoView = PhotoView.extend({
    className : 'photo cropped',
    
    renderImage : function (image) {
      this.$el.removeClass('imgwide imgtall');
      this.$el.append(image);
      
      
      var $img = $(image);
      var containerAspect = _.result(this, 'containerAspect') || this.$el.width() / this.$el.height();
      var imageAspect = image.width / image.height;
      
      // Determine the axis to be cropped.  This is represented as a boolean which is true
      // if the image is being cropped horizontally, false if vertically.
      var cropHorizontal = containerAspect < imageAspect; 
        
      // In order to center the image along the cropped axis, we calculate the percentage
      // difference between the image and the container along the cropped axis - the image
      // is always longer along the cropped axis.
      //  
      // After calculating the ratio along the cropped aspect, multiply it by 50 - this represents 
      // half of the ratio as a percentage, which is the value by which we will nudge the image
      // using CSS in order to properly center it.
      //
      // For images cropped vertically, multiply the ratio by 20 instead of 50.  This
      // is an attempt to get vertically cropped images to display a better portion of the photograph,
      // which is usually higher than the center.
      var ratio = cropHorizontal ? 
        (imageAspect - containerAspect) / containerAspect :   // Horizontal crop formula.
        (containerAspect / imageAspect) - 1;                  // Vertical crop formula.
      var percent = ratio * (cropHorizontal ? 50 : 20);
      
      if (cropHorizontal) {
        this.$el.addClass('imgwide');
        $img.css({
          'left' : String(-percent) + '%',
          'top' : ''
        });
      } else {
        this.$el.addClass('imgtall');
        $img.css({
          'top' : String(-percent) + '%',
          'left' : ''
        });
      }
    }
  });
  
  var ThumbnailPhotoView = CroppedPhotoView.extend({  

  });
  
  // Similar to cropped photo view, but zooming the image to double size.  Additionally, the
  // image is not centered in the vertical cropping case.
  var ZoomedPhotoView = CroppedPhotoView.extend({
    className : 'photo zoomed',
    
    renderImage : function (image) {
      this.$el.removeClass('imgwide imgtall');
      this.$el.append(image);
      
      var $img = $(image);
      var containerAspect = _.result(this, 'containerAspect') || this.$el.width() / this.$el.height();
      var imageAspect = image.width / image.height;
      
      // Determine the axis to be cropped.  This is represented as a boolean which is true
      // if the image is being cropped horizontally, false if vertically.
      var cropHorizontal = containerAspect < imageAspect; 
        
      var ratio = cropHorizontal ? 
        (imageAspect - containerAspect) / containerAspect :   // Horizontal crop formula.
        (containerAspect / imageAspect) - 1;                  // Vertical crop formula.
      var percent = ratio * 100;
      
      this.$el.addClass('crop');
      if (cropHorizontal) {
        this.$el.addClass('imgwide');
        $img.css('left', String(-percent) + '%');
        $img.css('top', '');
      } else {
        this.$el.addClass('imgtall');
        $img.css('top', String(-percent) + '%');
        $img.css('left', '');
      }
    },
    
    selectSize : function () {
      // Hack : currently, zoomed is only used for inbox rows, which should use medium images.
      return 'med';
    }
  });
  
  // Display a photo image in such a way that the entire image is shown as large as possible in
  // the container, while still preserving aspect ratio.
  var ConstrainedPhotoView = PhotoView.extend({
    className : 'photo constrained',
    
    renderImage : function (image) {
      this.$el.removeClass('imgwide imgtall');
      this.$el.append(image);
      
      var $img = $(image);
      var containerAspect = this.$el.width() / this.$el.height();
      var imageAspect = image.width / image.height;
      
      // Determine the axis to be filled.  This is represented as a boolean which is true
      // if the image is filling horizontally, false if vertically.
      var fillHorizontal = containerAspect < imageAspect; 
      
      this.$el.css('line-height', String(this.$el.height()) + 'px');
      if (fillHorizontal) {
        this.$el.addClass('imgwide');
      } else {
        this.$el.addClass('imgtall');
      } 
    }
  });


  // **********************************************************************************************
  //                                ROW LAYOUT VIEWS
  // **********************************************************************************************
  
  var minPhotoRowAspect = 9 / 5;
  var maxPhotoRowAspect = 9 / 2.5;
  
  // Displays a single photo within a row of photos.
  var WideEpisodePhotoView = ViewfinderView.extend({
    className : 'episode-photo',
    
    events : {
      'click' : 'selected'
    },
    
    initialize : function (options) {
      this.idealHeight = options.idealHeight;
      this.actualHeight = options.actualHeight;
      this.activity = options.activity;
    },
    
    render : function () {
      var w = this.idealHeight * this.model.get('aspect_ratio');
      this.$el.css('width', String(w) + '%');
      // Container aspect is an optimization.  Borders are a constant 1px, so we adjust the width and height
      // of the photo by 0.2%, which matches the percentage of the borders at a 1000px width.
      this.appendChild(CroppedPhotoView, { model : this.model, 
                                           scrollLoad : true, 
                                           border : true,
                                           containerAspect : (w - 0.2) / (this.actualHeight - 0.2) });
    },
    
    selected : function () {
      this.model.scope().selection.activity(this.activity);
      this.model.scope().selection.photo(this.model);
    }
  });
  
  var WideEpisodePhotosView = ViewfinderView.extend({
    className : 'episode-photos',
    
    initialize : function (options) {
      this.idealHeight = options.idealHeight;
      this.actualHeight = options.actualHeight;
      this.activity = options.activity;
    },
    
    render : function () {
      this.destroyChildren();
      
      var view = this;
      _(this.model.get('photos')).each(function (p) {
        view.appendChild(WideEpisodePhotoView, { 
          model : p, 
          activity : view.activity, 
          idealHeight : view.idealHeight, 
          actualHeight : view.actualHeight
          });
      });
      
      return this;
    }
  });
  
  // Displays a single row of photos.
  var WideEpisodeRowView = ViewfinderView.extend({
    className : 'episode-row',
    
    initialize : function (options) {
      this.activity = options.activity;
    },
    
    render : function () {
      this.destroyChildren();
      
      // ideal height as a percentage.
      var idealHeight = 100 / this.model.get('aspect');
      var actualHeight = idealHeight;
      actualHeight = Math.max(100 / maxPhotoRowAspect, actualHeight);
      actualHeight = Math.min(100 / minPhotoRowAspect, actualHeight);
      this.$el.css('padding-top', String(actualHeight) + '%');
      
      this.appendChild(WideEpisodePhotosView, {
        model : this.model,
        idealHeight : idealHeight,
        actualHeight : actualHeight,
        activity : this.activity
      });

      return this;
    }
  });
  
  
  // **********************************************************************************************
  //                                  EPISODE VIEWS
  // **********************************************************************************************
  
  
  // Display container for wide-format episodes.  Photos are laid out in rows, preserving aspect ratio.
  var WideEpisodeView = ViewfinderView.extend({
    className : 'episode',
   
    initialize: function(options) {
      this.debounceRender = _.simpleDebounce(this.render);
      this.listenTo(this.model, 'add:post change:post', this.debounceRender);
    },
    
    render : function () {
      this.destroyChildren();
      var view = this;
      var $view = this.$el;
      
      var photos = this.model.getSharedPhotos();

      // Exclude the cover photo in single-column layout.  
      if (layoutManager.layout() !== 'TwoCol') {
        var cover = this.model.getViewpoint().getCoverPhoto();
        photos = _(photos).without(cover);
      }

      if (photos.length === 0) {
        return this;
      }

      this.appendChild(EpisodeHeaderView, {model : this.model});
      
      // ***** LAYOUT SUPPORT FUNCTIONS *****
      
      // Recursive function to find all viable candidate combinations for laying out the next three rows.
      function recurseCombos(partial, photosReserved, combos) {
        if (combos.length >= 30) {
          // Consider a maximum of 30 combinations for any iteration of this.
          return;
        }
        
        if (partial.length === 3 || photosReserved === photos.length) {
          // If the partial combo contains three rows OR we are out of photos, this combination is complete.
          combos.push(partial);
          return;
        }
        
        // For the current partial combination, compute possibilities for the next row.  We will consider
        // each row of ideal height, plus up to one overheight and one underheight row.
        var row = [];
        var aspect = 0;
        var overheightRow = null;
        var i;
    
        for (i = photosReserved; i < photos.length; i += 1) {
           // Add photo to next row.
          row = row.slice(0);
          row.push(photos[i]);
          
          // Calculate ideal height of this row, preserving aspect.
          aspect += photos[i].get('aspect_ratio');
          
          if (aspect < minPhotoRowAspect) {
            overheightRow = [row, i];
          } else {
            // Add this row to the current partial combination and calculate
            // the next set of possible rows.
            recurseCombos(partial.concat([row]), i + 1, combos);
            if (aspect < maxPhotoRowAspect) {
              break;
            }
          }
        } 
        
        if (overheightRow) {
          recurseCombos(partial.concat([overheightRow[0]]), overheightRow[1] + 1, combos);
        }
      }
      
      // Function to get the aspect ratio of a completed row.
      function rowAspect(row) {
        var aspect = 0;
        var i;
        for (i = 0; i < row.length; i += 1) {
          aspect += row[i].get('aspect_ratio');
        }
        
        return aspect;
      }
      
      // Function to determine the 'score' of a single potential row.  0 is a perfect score, higher
      // is worse.
      function rowScore(row) {
        var aspect = rowAspect(row);
        if (aspect > maxPhotoRowAspect) {
          return Math.pow(10, (aspect / maxPhotoRowAspect)) - 10;
        }
        
        if (aspect < minPhotoRowAspect) {
          return Math.pow(10, (minPhotoRowAspect / aspect)) - 10;
        }
        
        return 0;
      }
      
      // Function to determine the total score of a possible row combination.
      function comboScore(combo) {
        // TODO(matt): Add some score adjustments considering the entire combination, 
        //             rather than just individual rows.
        return _(combo).sum(rowScore);
      }
          
      // ***** LAYOUT ALGORITHM *****
      // From the full list of photos for this episode, repeatedly carve off individual rows of photos.
      // Rows will be selected to ensure a minimal amount of cropping while maintaining the aspect ratio
      // of each individual photo.
      
      var finishedRows = [];
      while (photos.length > 0) {
        // To determine the next row, lay out the next three rows in ideal fashion and take the first row.
        // This is accomplished by calculating a number of possible combinations for the next three rows
        // and scoring each combination.  The first row of the highest scoring combination will be accepted.
        
        // Completed candidate combinations.  A combination is an array of rows.  Each row is an array of photos.
        var combos = [];  

        // Starting with an empty row combination, recursively find a list of good candidates.
        recurseCombos([], 0, combos);
        
        // Sort row combinations by total score.
        combos = _(combos).sortBy(comboScore);

        var newRow = combos[0][0];
        photos = photos.slice(newRow.length);
        finishedRows.push(new Backbone.Model({
          photos : newRow,
          aspect : rowAspect(newRow)
        }));
      }
      
      _(finishedRows).each(function (row) {
        view.appendChild(WideEpisodeRowView, {model : row, activity : view.model});
      });

      return this;
    }
  });

  // **********************************************************************************************
  //                                  EPISODE VIEWS
  // **********************************************************************************************
  var AccountInfoView = ViewfinderView.extend({
    className : 'account-info',

    templateName : 'account-info',

    render : function() {
      var name = this.model.getFullName();
      this.$el.html(this.template()({ name : name }));
      return this;
    }
  });
 
    
  // **********************************************************************************************
  //                                  CONVERSATION VIEWS
  // **********************************************************************************************

  // Displays an indicator next to items which have not yet been viewed by the user.
  var UnviewedItemView = ViewfinderView.extend({
    className : 'unviewed-item scrolleffect',

    render : function () {
      var $view = this.$el;
      var model = this.model;

      if (!model.isViewed()) {
        this.listenToOnce(this.model, 'change:viewed_seq', this.render);
        $view.on('scrolleffect', function () {
          model.setViewed();
          $view.off('scrolleffect');
        });
      } else {
        $view.off('scrolleffect');
        _.delay(function () {
          $view.addClass('viewed');
        }, 2000);
      }     

      return this;
    }
  });

  // Displays the header for a single episode.
  var EpisodeHeaderView = ViewfinderView.extend({
    className : 'episode-header activity-info',
    
    templateName : 'episode-header',
    
    initialize : function () {
      this.debounceRender = _.simpleDebounce(this.render);
      this.bindModel('add:post change:post change:user', this.debounceRender); 
      this.bindModel('ui:locate', this.scrollTo);
    },
    
    render : function () {
      // Check photo count - don't display if there are no photos.
      // This can occur due to either incomplete loading or unsharing.
      var count = this.model.getPhotoCount();
      if (count === 0) {
        this.$el.empty();
        return this;
      }
      
      // Activity header contains basic information.
      var user = this.model.getPostingUser().getDisplayName();
      var time = new Date(this.model.get('timestamp') * 1000);
      var loc = this.model.getLocationString();

      this.$el.html(this.template()({user : user, loc : loc}));
       
      if (time) {
        this.assignChild('.timestamp', TimestampView, {timestamp:time, format:'short'});
      }

      return this;
    },
    
    scrollTo : function () {
      $('html, body').scrollTop(this.$el.offset().top - 133);
    }
  });


  
  // Displays an activity header.
  var CommentView = ViewfinderView.extend({
    className : 'comment activity-info',
    
    templateName : 'comment',
    
    initialize : function () {
      this.bindModel('change:comment change:user', this.render);
    },
    
    events : {
      'click .photo' : 'onClickHighlight'
    },
    
    render : function () {
      this.destroyChildren();
      this.$el.removeClass('highlight');

      var user = '';
      var time = null;
      var message = '';
      var highlight = null;
      
      var comment = this.model.getComment();
      if (!comment.isPlaceholder()) {
        user = comment.getUser().getDisplayName();
        time = new Date(comment.get('timestamp') * 1000);
        message = comment.get('message');
      }
        
      highlight = comment.getHighlightPhoto();

      this.$el.html(this.template()({
        user : user,
        message : this.escapeMessage(message)
      }));
      
      if (time) {
        this.assignChild('.timestamp', TimestampView, {timestamp:time, format:'short'});
      }
      
      if (highlight) {
        this.$el.addClass('highlight');
        this.appendChild(ThumbnailPhotoView, { model : highlight, containerAspect : 1});
      }
      
      return this;
    },

    escapeMap : {
      '&' : '&amp;',
      '<' : '&lt;',
      '>' : '&gt;'
    },

    // URL regular expression.  On the advice of Jeff Atwood, we will allow parenthesis in 
    // the URLs (which are allowed an used often by places like wikipedia), but will try to 
    // account for the case where the URL is wrapped in parenthesis and the trailing close
    // paren is not actually part of the URL (a confusing case, but it seems worthwhile.)
    //
    // See: http://www.codinghorror.com/blog/2008/10/the-problem-with-urls.html
    //
    urlExp : /\(?(\b((https?|ftp):\/\/|www\.)[-A-Za-z0-9+&@#\/%?=~_|\(\)!:,.;]*[-A-Z0-9+&@#\/%=~_|\(\)])/ig,

    escapeMessage : function (message) {
      var result;
      // Escape HTML special characters from the original message.
      var escapeMap = this.escapeMap;
      message = message.replace(/[&<>]/g, function (m) { return escapeMap[m]; });

      // Replace newlines with line break tags.
      message = message.replace(/\n/g, '<br />');

      // Extract URLs, replacing them with anchor tags.
      return message.replace(this.urlExp, function (match) {
        var wrappingParens = match.startsWith('(') && match.endsWith(')');
        if (wrappingParens) {
          match = match.substring(1, match.length - 1);
        }

        var anchor = '<a href="' + match + '" target="_blank">' + match + '</a>';
        return wrappingParens ? '(' + anchor + ')' : anchor;
      });
    },
    
    onClickHighlight : function () {
      var highlight = this.model.getComment().getHighlightPhoto();
      var activity = this.model.getViewpoint().findActivity(highlight);
      
      if (activity) {
        var select = this.model.scope().selection;
        select.activity(activity);
        select.photo(highlight);
      }
    }
  });

  var ShareNewView = ViewfinderView.extend({
    className : 'share-new activity-info',

    templateName : 'share-new',

    initialize : function () {
      this.bindModel('change:user', this.render());
      this.bindMinorLayoutChange(this.render);
    },

    render : function () {
      var ml = layoutManager.minorLayout();
      var tmpl = ml === 'wide' ? 'share-new-wide' : 'share-new';

      this.$el.html(this.template(tmpl)({
        user : this.model.getPostingUser().getDisplayName()
      }));

      var time = new Date(this.model.get('timestamp') * 1000);
      this.assignChild('.timestamp', TimestampView, {timestamp:time, format:'short'});
    }
  });

  // Displays an Add followers activity, which has a special appearance.
  var AddFollowersView = ViewfinderView.extend({
    className : 'addfollowers activity-info',

    templateName : 'add-followers',
    
    initialize : function () {
      // User changes are rare - just bind to the follower collection of the viewpoint,
      // and re-render if any user changes.
      var followers = this.model.getViewpoint().followers;
      this.listenTo(followers, 'change:user', this.render);
      this.bindMinorLayoutChange(this.render);
    },
    
    render : function () {
      this.destroyChildren();
      var poster = this.model.getPostingUser().getDisplayName(true);
      var added = _(this.model.getAddedFollowers()).map(function (f) {
        return f.getDisplayName(true); 
      });

      var ml = layoutManager.minorLayout();
      var tmpl = ml === 'wide' ? 'add-followers-wide' : 'add-followers';

      this.$el.html(this.template(tmpl)({
        poster : poster,
        added : added.join(', ')
      }));

      var time = new Date(this.model.get('timestamp') * 1000);
      if (time) {
        this.assignChild('.timestamp', TimestampView, {timestamp:time, format:'short'});
      }
      return this;
    }
  });
 
 
  // Displays a single activity, which may contain a comment, an episode, or some other information.
  var ActivityView = ViewfinderView.extend({
    className : 'activity',

    displayTypes : ['post_comment', 'share_existing', 'upload_episode', 'add_followers', 'share_new'],
    
    render : function () {
      var view = this;
      var $view = this.$el;
      
      var type = view.model.get('type'); 

      if (!_(this.displayTypes).contains(type)) {
        return this;
      }

      if (!view.model.isViewed()) {
        view.appendChild(UnviewedItemView, {model : view.model.getViewpoint()});
      }
      
      if (type === 'add_followers') {
        view.appendChild(AddFollowersView, {model : view.model});
      } else if (type === 'post_comment') {
        view.appendChild(CommentView, {model : view.model});
      } else {
        if (type === 'share_new') {
          view.appendChild(ShareNewView, {model : view.model});
        }

        if (view.model.getSharedEpisodes()) {
          view.appendChild(WideEpisodeView, {model : view.model });
        }
      }

      return this;
    },

    isChainable : function(view) {
      var type = this.model.get('type');
      return (type === 'post_comment');
    },

    isShare : function(view) {
      var type = this.model.get('type');
      return (type === 'share_new' || type === 'share_existing');
    }
  });

  
  // Displays a collection of activities within a conversation.  Maintains the proper display order
  // for the activities based on information from the model.
  var ConversationActivitiesView = CollectionView.extend({
    className : 'conversation-activities',
    
    initialize : function () {
      this.debounceRender = _.simpleDebounce(this.render);
      this.bindCollection('add', this.debounceRender);
    },
    
    render : function () {
      var parentView = this;
      var lastView = null;
      var mergedStart = null;
      var mergedViews = [];
      var alt = true;

      // TODO(matt): Activities which are hidden by virtue of unshare events are 
      // still being included in the 'alt' pattern calculation - this requires some
      // more clever work in the activity view to support.  FIX IT.
      this.renderCollection(this.collection, ActivityView, function(view) {
        view.$el.removeClass('link-prev link-next merge-prev merge-next alt');
        if (lastView && view.isChainable()) {
          // For chainable views, we visually link this activity with the previous one
          // if it occured within one hour of the previous activity - an exception is made
          // for comment which have a highlight photo.
          if (lastView.isChainable() &&
              (!view.model.getComment() || ! view.model.getComment().getHighlightPhoto()) &&
              (view.model.get('timestamp') - lastView.model.get('timestamp')) < 60 * 60) {

            if (lastView.model.get('user_id') === view.model.get('user_id')) {
              // We further combine consecutive posts by the same user, giving them the
              // appearance of being a single activity.

              mergedStart = mergedStart || lastView;
              mergedViews.push(view);
              view.$el.addClass('merge-prev');
              lastView.$el.addClass('merge-next');
            } else {
              // If any of the previous views had been merged together, we now apply
              // linking to them as a whole.
              if (mergedStart) {
                mergedStart.$el.addClass('link-next');
                var i = 0;
                for (i = 0; i < mergedViews.length;  i++) {
                  mergedViews[i].$el.addClass('link-next link-prev');
                }

                mergedStart = null;
                mergedViews.length = 0;
              }

              view.$el.addClass('link-prev');
              lastView.$el.addClass('link-next');
              alt = !alt;
            }
          } else {
            mergedStart = null;
            mergedViews.length = 0;
            alt = !alt;
          }
        } else if (view.isShare()) {
          view.$el.addClass('link-next');
        } else if (view.model.get('type') === 'add_followers') {
          alt = !alt;
        }

        if (alt) {
          view.$el.addClass('alt');
        }

        lastView = view;
      });
      return this;
    }
  });
  

  // Display the header for a conversation.
  var ConversationInfoView = ViewfinderView.extend({
    className : 'conversation-header',
    
    templateName : 'conversation-header',
    
    initialize : function () {
      this.debounceRender = _.simpleDebounce(this.render);
      this.bindModel('change:title change:loaded', this.render);
      this.listenTo(this.model.activities, 'add:post change:post', this.debounceRender);
      this.listenTo(this.model.followers, 'add change:user', this.debounceRender);
    },
    
    render : function() {
      var users = this.model.followers.getActiveUsers();
      var userNames = _(users).map(function (f) {
        return f.getDisplayName();
      });

      this.$el.html(this.template()({
        title : this.model.getTitle(),
        followers : userNames.join(', '),
        photoCount : this.model.getPhotoCount(),
        commentCount : this.model.getCommentCount()
      }));
      
      return this;
    }
  });
 
 
  // Mask which covers the hero image before the conversation is loaded.
  var HeroMaskView = ViewfinderView.extend({
    className : 'hero-mask',
    
    templateName : 'hero-mask',
   
    render : function () {
      this.$el.html(this.template()());
      
      // If this is a placeholder viewpoint (whic
      
      // Always show mask if there is no background image.
      var cover = this.model.getCoverPhoto();
      if (!cover) {
        return this;
      }
      
      // Don't display mask if the conversation is loaded.
      var $view = this.$el;
      if (this.model.loaded()) {
        $view.css('opacity', 0);
      } else {
        if (viewfinder.fx.animation) {
          $view.addClass('fade-slow');
        }
        this.listenToOnce(this.model, 'change:loaded', this.render);
      }
      
      return this;
    }
  });
  

  // Conversation Hero image view.
  var ConversationCoverView = ViewfinderView.extend({
    className : 'conversation-cover',
    
    initialize : function () {
      this.bindModel('change:cover', this.render);
    },
    
    events : {
      'click' : 'onClick'
    },
    
    render : function() {
      this.destroyChildren();    
      var loaded = this.model.loaded();
      var cover = this.model.getCoverPhoto();
    
      if (cover) {
        this.appendChild(CroppedPhotoView, {model : cover, containerAspect : 1.538, size : 'full'});
      }
      
      if (!cover) {
        this.appendChild(HeroMaskView, {model : this.model});
      }
      
      return this;
    },
    
    onClick : function () {
      if (!this.model.loaded()) {
        return;
      }
      
      var cover = this.model.getCoverPhoto();
      if (!cover) {
        return;
      }
      
      var activity = this.model.findActivity(cover);
      if (activity) {
        var select = this.model.scope().selection;
        select.activity(activity);
        select.photo(cover);
      }
    }
  });  
  
  var SignupCtaView = SimpleTemplateView.extend({
    className : 'add-comment',

    templateName : 'signup-cta',

    initialize : function () {
      // Can't use scrolleffect - scrolleffect is optimized for one time events.
      if (viewfinder.fx.fixed) {
        this.bindScroll(this.onScroll);
      } else {
        this.$el.addClass('static');
      }
    },

    render : function () {
      SimpleTemplateView.prototype.render.apply(this);
      this.onScroll();
    },

    onScroll : function () {
      var $w = $(window);
      var bottom = $w.scrollTop() + (window.innerHeight ? window.innerHeight : $w.height());
      var height = 50;
      if ((this.$el.offset().top) + height < bottom) {
        this.$el.addClass('static');
      } else {
        this.$el.removeClass('static');
      }
    }
  });

  // Dialog for users to add a comment.
  var AddCommentDialogView = FormDialogBaseView.extend({
    className : 'add-comment',

    templateName : 'add-comment',

    initialize : function (options) {
      FormDialogBaseView.prototype.initialize.apply(this);

      this.viewpoint = options.viewpoint;

      this.bindModel('reset', function () {
        layoutManager.trigger('resetPolling');
        this.form.setValue('message', '');
        this.scrollTo();
      });

      this.bindModel('change:requestInProgress', this.setInstruction);

      this.listenTo(this.form, 'focus blur', function () {
        if (this.form.hasFocus) {
          this.$el.addClass('focus');
          this.scrollTo();
        } else {
          this.$el.removeClass('focus');
        }
      });

      // Can't use scrolleffect - scrolleffect is optimized for one time events.
      if (viewfinder.fx.fixed) {
        this.bindScroll(this.onScroll);
      } else {
        this.$el.addClass('static');
      }
    },

    render : function () {
      FormDialogBaseView.prototype.render.apply(this);
      this.onScroll();
    },

    formSchema : {
      message : {type:'TextArea', editorAttrs : { placeholder : 'write a comment' }, template : FormFieldTemplate }
    },

    scrollTo : function () {
      $('html, body').animate({ scrollTop :this.$el.offset().top }, 200);
    },

    onCancel : function () {
      this.model.set('message', '');
    },

    onScroll : function () {
      if (!this.viewpoint.loaded()) {
        // Do nothing until viewpoint is loaded. 
        return;
      }

      var $w = $(window);
      var bottom = $w.scrollTop() + (window.innerHeight ? window.innerHeight : $w.height());
      var height = 50;
      if ((this.$el.offset().top) + height < bottom) {
        this.$el.addClass('static');
      } else {
        this.$el.removeClass('static');
      }
    },

    setInstruction : function () {
      var message = this.model.get('requestInProgress') ? 'Submitting comment...' : 'Enter to submit';
      this.$('.instruction').text(message);
    }
  });

  // Display the body for the conversation.  The contents of the body varies based on screen width.
  var ConversationBodyView = ViewfinderView.extend({
    className : 'conversation-body',
    
    initialize : function () {
      this.bindModel('change:loaded', this.render);
    },
    
    render : function () {
      this.destroyChildren();
      if (this.model.loaded()) { 
        this.$el.removeClass('loading');
        this.appendChild(ConversationActivitiesView, {collection : this.model.activities});
      } else {
        this.$el.addClass('loading');
      }
      
      return this;
    }
  });


  // **********************************************************************************************
  //                                SELECTED CONVERSATION
  // **********************************************************************************************
    
  // A view which displays the currently selected conversation within a collection of 
  // materialized conversations.
  var SelectedConversationView = ViewfinderView.extend({
    className : 'conversation',
    
    initialize : function () {
      this.bindModel('change:viewpoint', this.render);
      this.bindLayoutChange(this.render);
      this.bindMinorLayoutChange(this.setMinorLayout);

      if (viewfinder.fx.fixed) {
        this.$el.addClass('fixed-header');
      }

      this.setMinorLayout();
    },
    
    render : function () {
      this.destroyChildren();   
      var viewpoint = this.model.viewpoint();
      if (!viewpoint) {
        return this;
      }

      var layout = layoutManager.layout();

      if (viewpoint.isPlaceholder()) {
        // Initial viewpoint selection may be a placeholder - just display nothing
        // and render again when it is no longer a placeholder.
        this.listenToOnce(viewpoint, 'change', this.render);
      } else {
        this['render' + layout]();
        this.assignChild('.cover', ConversationCoverView, {model : viewpoint});
        this.assignChild('.info', ConversationInfoView, {model : viewpoint});
        this.assignChild('.collection', ConversationBodyView, {model : viewpoint});
      }
      
      return this; 
    },

    renderMobile : function () {
      this.$el.html(this.template('conversation-mobile')());
    },

    renderOneCol : function () {
      this.$el.html(this.template('conversation-one-col')());
    },

    renderTwoCol : function () {
      this.$el.html(this.template('conversation-two-col')());
    },

    setMinorLayout : function () {
      var ml = layoutManager.minorLayout();
      this.$el.removeClass('wide thin');
      if (ml === 'wide') {
        this.$el.addClass('wide');
      } else {
        this.$el.addClass('thin');
      }
    }
  });
  
  
  // **********************************************************************************************
  //                                    INBOX VIEW
  // **********************************************************************************************
  
  // Element at the bottom of inbox to manage 'infinite-scroll' paging.
  var InboxPagerView = ViewfinderView.extend({
    className : 'inbox-pager scrolleffect',
    
    initialize : function () {
      this.bindModel('change:lastQueryFollowedKey', this.render);
    },
    
    render : function () {
      var $view = this.$el;
      var net = this.model;
      
      if (net.get('lastQueryFollowedKey')) {
        $view.on('scrolleffect', function () {
          $view.off('scrolleffect');
          net.continueQueryFollowed();
        });
      } else {
        $view.off('scrolleffect');
      }
      
      return this;
    }
  });

  // Optimization: Store the aspect of inbox photos whenever the inbox resizes, so that we
  // don't have to recalculate it for each image.
  var inboxPhotoAspect = 400 / 170;
  
  // Displays a single row in the 'Inbox'.
  var InboxRowView = ViewfinderView.extend({
    className : 'inbox-row card',
    
    templateName : 'inbox-row',
    
    events : {
      'click' : 'select'
    },
    
    initialize : function () {
      this.prospective = !viewfinder.flags.isRegistered 
        && (this.model.get('type') !== 'system' && this.model.id !== viewfinder.viewpoint_id);
      this.debounceRender = _.simpleDebounce(this.render);
      this.bindModel('change', this.debounceRender);
      this.listenTo(this.model.followers, 'add change:user', this.debounceRender);
      this.bindModel('ui:locate', this.scrollTo);
    },
    
    render : function () {
      this.destroyChildren();

      // Hide conversations which are removed or are still placeholders.
      var hide = this.model.isRemoved() || this.model.isPlaceholder();
      if (hide) this.$el.empty();
      this.$el.toggleClass('removed', hide);

      // Prospective inbox appearance: other than the one conversation the user can view in this
      // session, inbox rows have a 'preview' appearance.
      this.$el.toggleClass('prospective', this.prospective);
      this.$el.toggleClass('unviewed', !this.prospective && !this.model.isViewed());
      
      var users = this.model.followers.getActiveUsers();
      var userNames = _(users).map(function (f) {
        return f.getDisplayName(true);
      });

      this.$el.html(this.template()({
        title : this.model.getTitle(),
        followers : userNames.join(', ')
      }));

      var cover = this.model.getCoverPhoto();
      this.$el.toggleClass('no-photo', !cover);
      if (cover) {
        this.appendChild(CroppedPhotoView, { model : cover, 
                                             containerAspect : this.containerAspect, 
                                             dynamicResize : true});
      }
      
      var time = this.model.get('last_updated');
      if (time) {
        this.assignChild('.timestamp', TimestampView, {timestamp:new Date(time * 1000), format:'short'});
      }
      
      return this;
    },

    containerAspect : function () {
      return inboxPhotoAspect;
    },
    
    select : function () {
      if (!this.prospective) {
        this.model.scope().selection.viewpoint(this.model);
      }
    },

    scrollTo : function () {
      $('html, body').scrollTop(this.$el.offset().top - 50);
    }
  });
  
  // Displays an 'Inbox' of conversations.
  var InboxCollectionView = CollectionView.extend({
    className : 'inbox-collection', 
    
    initialize : function () {
      var debounceRender = _.simpleDebounce(this.renderRows);
      this.bindCollection('add sort', debounceRender);
    },
    
    render : function () {
      this.renderRows();
      return this;
    },

    renderRows : function () {
      var collection = this.collection.getActive().reverse();
      this.renderCollection(collection, InboxRowView);
    }
  });

  var InboxView = ViewfinderView.extend({
    className : 'inbox',

    initialize : function (options) {
      this.network = options.network;

      this.bindLayoutChange(this.render);
      this.bindResize(this.onResize);
      this.prospective = !viewfinder.flags.isRegistered;
      var imgsrc = this.prospective ?
            'web_code/images/prospective_dashboard.jpg' :
            'web_code/images/default_dashboard.jpg';
      this.bgModel = viewfinder.models.PhotoModel.createStatic(imgsrc);
      this.onResize($(window));
      this.render();
    },

    render : function () {
      this.destroyChildren();
      var layout = layoutManager.layout();
      this['render' + layout]();
      this.assignChild('.collection', InboxCollectionView, {collection : this.collection});
      this.assignChild('.inbox-pager', InboxPagerView, {model : this.network});
    },

    renderMobile : function () {
      this.$el.html(this.template('inbox-mobile-col')({
        prospective : this.prospective
      }));
    },

    renderOneCol : function () {
      this.$el.html(this.template('inbox-one-col')({
        prospective : this.prospective
      }));
      this.assignChild('.photo', CroppedPhotoView, {model : this.bgModel, containerAspect : 2});

      if (!this.prospective) {
        var own_user = this.collection.scope().users.get(viewfinder.own_user.user_id);
        this.assignChild('.account-info', AccountInfoView, { model : own_user });
      }
    },

    renderTwoCol : function () {
      this.$el.html(this.template('inbox-two-col')({
        prospective : this.prospective
      }));

      if (this.prospective) {
        this.assignChild('.photo', CroppedPhotoView, {model : this.bgModel, dynamicResize : true});
      } else {
        this.assignChild('.photo', CroppedPhotoView, {model : this.bgModel, containerAspect : 1.25});
        var own_user = this.collection.scope().users.get(viewfinder.own_user.user_id);
        this.assignChild('.account-info', AccountInfoView, { model : own_user });
      }
    },

    onResize : function ($window) {
      var w = $window.width();
      var layout = layoutManager.layout();
      
      switch(layout) {
      case 'Mobile':
        inboxPhotoAspect = ((w - 18) * 0.4) / 140; 
        break;
      case 'OneCol':
        inboxPhotoAspect = ((w - 18) * 0.4) / 170;
        break;
      case 'TwoCol':
        inboxPhotoAspect = (Math.min(((w * 0.625) - 18), 800) * 0.4) / 170;
        break;
      }
    }
  });
  
  // **********************************************************************************************
  //                                    GALLERY VIEW
  // **********************************************************************************************
  
  var GalleryPhotoView = ViewfinderView.extend({
    className : 'gallery-photo',
    
    initialize : function () {
      this.mode = this.options.mode;
      this.bindModel('change:photo', this.render);
    },
    
    render : function () {
      if (this.mode) {
        this.$el.addClass(this.mode);
      }
      
      this.destroyChildren();    
      
      var photo = this.model.photo();
      var viewType = PhotoView;
      
      // Center photo has dynamic aspect; 'prev' and 'next' teasers are constrained to a
      // constant height.
      var options = {};
      options.model = photo;
      options.dynamicResize = true;
      viewType = ConstrainedPhotoView;
            
      if (!options.model) {
        return this;
      }
      
      this.appendChild(viewType, options);
      return this;
    }
  });
  
  // Displays the header for a single episode.
  var GalleryInfoView = ViewfinderView.extend({
    className : 'gallery-info',
    
    templateName : 'gallery-info',
    
    initialize : function () {
      this.bindModel('change:photo', this.render);
    },
    
    render : function () {
      this.destroyChildren();
      var photo = this.model.photo();
      var activity = this.model.activity();
      if (!photo || !activity) {
        return this;
      }
      
      var loc = photo.getLocationString();
      var user = activity.getPostingUser().getDisplayName();
      this.$el.html(this.template()({loc : loc, user : user}));

      var time = new Date(photo.get('timestamp') * 1000);
      time = time || this.model.get('minTime');
      if (time) {
        this.assignChild('.timestamp', TimestampView, {timestamp:time, format:'short'});
      }
       
      return this;
    }
  });

  var GalleryCountView = ViewfinderView.extend({
    className : 'gallery-count',
    
    templateName : 'gallery-count',
    
    initialize : function () {
      this.bindModel('change:index', this.render);
    },
    
    render : function () {
      var index = this.model.get('index');
      var total = this.model.get('posts').length;
      this.$el.html(this.template()({ index : index + 1, total : total}));
      return this;
    }
  });
  
  var GalleryPhotosView = ViewfinderView.extend({
    className : 'gallery-photos',
    
    render : function () {
      this.destroyChildren();
      return this;
    }
  });
    
  var GalleryDisplayView = ViewfinderView.extend({
    className : 'gallery-display',
    
    templateName : 'gallery-display',

    events : {
      'click .back' : 'close',
      'click .next' : 'next',
      'click .curr' : 'next',
      'click .prev' : 'prev',
      'mousedown' : 'suppress',
      'mousewheel' : 'suppress',
      'touchmove' : 'suppress',
      'swipeleft' : 'next',
      'swiperight' : 'prev'
    },
    
    render : function () {
      this.$el.html(this.template()());
      this.appendChild(GalleryPhotoView, {model : this.model});
      this.assignChild('.gallery-info', GalleryInfoView, {model: this.model});
      this.assignChild('.gallery-count', GalleryCountView, {model: this.model});
      this.bindModel('change:photo', this.changePhoto);
      this.bindKeydown(this.onKeydown);

      if (!viewfinder.fx.fixed) {
        this.$el.addClass('nofixed');
        this.bindScroll(this.adjustWindow);
        this.bindResize(this.adjustWindow);
        this.adjustWindow();
      } else {
        this.bindModel('change:activity', this.changeActivity);
      }

      this.changePhoto();
      this.$el.hammer({ stop_browser_behavior : false });
      this.delegateEvents();
      return this;
    },

    onDestroy : function () {
      if (!viewfinder.fx.fixed) {
        var oldActivity = this.model.previous('activity');
        if (oldActivity) {
          oldActivity.trigger('ui:locate');
        }
      }
    },

    onKeydown : function (e) {
      if (e.keyCode === 37) { // Left
        this.model.movePrevPhoto();
      } else if (e.keyCode === 39) {
        this.model.moveNextPhoto();
      } else if (e.keyCode === 27) {
        this.model.activity(null);
      }
    },

    close : function (e) {
      // Handle this through the router.
      this.model.activity(null);
      e.stopPropagation();
    },
    
    next : function (e) {
      this.model.moveNextPhoto();
      e.stopPropagation();
    },
    
    prev : function (e) {
      this.model.movePrevPhoto();
      e.stopPropagation();
    },
    
    suppress : function (e) {
      // Prevent selection on mousedown - a very annoying artifact of clicking.
      e.preventDefault();
    },

    changeActivity : function () {
      var activity = this.model.activity();
      if (activity) {
        activity.trigger('ui:locate');
      }
    },

    changePhoto : function () {
      this.$el.removeClass('nonext noprev');
      if (!this.model.nextPhoto()) {
        this.$el.addClass('nonext');
      }

      if (!this.model.prevPhoto()) {
        this.$el.addClass('noprev');
      }
    },

    adjustWindow : function () {
      var $w = $(window);
      var h = window.innerHeight;
      var top = $w.scrollTop();
      this.$el.css({
        height : h,
        top : top
      });
    }
  });
  
  
  var GalleryView  = ViewfinderView.extend({
    className : 'gallery',
    
    initialize : function () {
      this.bindModel('change:photo', function () {
        var curr = this.model.photo();
        var prev = this.model.previous('photo');
        
        // Only trigger render if changing from null to non-null photo, or vice-versa.
        if ((curr && !prev) || (!curr && prev)) {
          this.render();
        }
      });
    },
    
    render : function () {
      this.destroyChildren();
      if (this.model.photo()) {
        this.$el.css('display', 'block');
        this.appendChild(GalleryDisplayView, {model : this.model});
      } else {
        this.$el.css('display', 'none');
      }
      
      return this;
    }
  });
  
  // **********************************************************************************************
  //                                   AUTHORIZIATION FORMS
  // **********************************************************************************************  
  
  
  // LOGIN VIEWS
  // ***********
  var LoginBeginView = FormDialogBaseView.extend({
    className : 'auth-form login-begin',
    
    templateName: 'login-begin',
    
    formSchema : {
      identity_key : { editorAttrs : { placeholder : 'Email Address / Phone Number' }, template : FormFieldTemplate, dataType : 'email' },
      password : { editorAttrs : { placeholder : 'Password'}, type : 'Password', template : FormFieldTemplate },
      keep_cookie : { type : 'Checkbox', template : CheckboxTemplate, 
                      title : 'Remember Me' }
    },
    
    subOption : function () {
      this.model.resetMode();
    }
  });
  
  
  var LoginSuccessView = DialogBaseView.extend({
    className : 'auth-form login-success',
    
    templateName : 'login-success',
    
    render : function () {
      this.$el.html(this.template()({ given_name : this.model.get('given_name') }));
      _.delay(function () {
        window.location.href = '/view';
      }, 200);
    },

    onSubmit : function () {
      window.location.href = '/view';
    }
  });
  
  // REGISTER VIEWS
  // **************
  var RegisterBeginView = FormDialogBaseView.extend({
    className : 'auth-form register-begin',
    
    templateName : 'register-begin',
    
    formSchema : {
      identity_key : { editorAttrs : { placeholder : 'Email Address / Phone Number', disabled : true }, template : FormFieldTemplate },
      password : { editorAttrs : { placeholder : 'Create Password'}, type : 'Password', template : FormFieldTemplate },
      given_name : { editorAttrs : { placeholder : 'First Name'}, template : FormFieldTemplate },
      family_name : { editorAttrs : { placeholder : 'Last Name'}, template : FormFieldTemplate }
    },

    templateData : function () {
      return {
        identity_key : this.model.get('identity_key')
      };
    },
    
    subOption : function () {
      this.model.mergeMode();
    }
  });
  
  
  var RegisterTokenView = FormDialogBaseView.extend({
    className : 'auth-form register-token',
    
    templateName : 'register-token',

    formSchema : {
      access_token : { editorAttrs : { placeholder : 'Access Token' }, template : FormFieldTemplate }
    },

    templateData : function () {
      return {
        email : this.model.get('identity').split(':')[1]
      };
    }
  });
  
  var RegisterSuccessView = DialogBaseView.extend({
    className : 'auth-form register-success',
    
    templateName : 'register-success',
    
    render : function () {
      this.$el.html(this.template()({ given_name : this.model.get('given_name') }));
      return this;
    },

    onSubmit : function () {
      window.location.href = '/view';
    }
  });
  
  
  // RESET VIEWS
  // ***********
  var ResetBeginView = FormDialogBaseView.extend({
    className : 'auth-form reset-begin',
    
    templateName: 'reset-begin',
    
    formSchema : {
      identity_key : { editorAttrs : { placeholder : 'Email Address / Phone Number' }, template : FormFieldTemplate, dataType : 'email' }
    },
    
    onCancel : function () {
      this.model.prevMode();
    }
  });

  var ResetTokenView = RegisterTokenView.extend({
    className : 'auth-form reset-token',

    templateName : 'reset-token'
  });  
  
  var ResetPasswordView = FormDialogBaseView.extend({
    className : 'auth-form reset-password',
    
    templateName: 'reset-password',
    
    formSchema : {
      identity_key : { editorAttrs : { disabled : true }, template : FormFieldTemplate },
      password : { 
        type : 'Password',
        editorAttrs : { placeholder : 'New Password'}, 
        validators : [{ type : 'match', field : 'confirm_password', message : 'Passwords did not match. Try again.'}],
        template : FormFieldTemplate 
      },
      confirm_password : { type: 'Password', editorAttrs : { placeholder : 'Confirm New Password'}, template : FormFieldTemplate }
    }
  });
 
  var ResetSuccessView = DialogBaseView.extend({
    className : 'auth-form reset-success',
    
    templateName : 'reset-success',
    
    render : function () {
      this.$el.html(this.template()({ user_name : this.model.get('user_name') }));
      return this;
    },

    onSubmit : function () {
      window.location.href = '/view';
    }
  });

  var ResetSuccessMergeView  = DialogBaseView.extend({
    className : 'auth-form reset-success-merge',

    templateName : 'reset-success-merge',

    render : function () {
      this.$el.html(this.template()());
      return this;
    }
  });
  

  // MERGE VIEWS
  // ***********  
  var MergeBeginView = LoginBeginView.extend({
    className : 'auth-form merge-begin',
    
    templateName: 'merge-begin',
    
    templateData : function () {
      return {
        source : this.model.get('source_identity').split(':')[1]
      };
    },

    subOption : function() {
      this.model.resetMode();
    },

    onCancel : function() {
      this.model.prevMode();
    }
  });

  var MergeConfirmView = DialogBaseView.extend({
    className : 'auth-form merge-confirm',
    
    templateName : 'merge-confirm',
    
    render : function () {
      this.destroyChildren();
      this.$el.html(this.template()({ 
        name : this.model.get('given_name'),
        target : this.model.get('identity_key'), 
        source : this.model.get('source_identity').split(':')[1]
      }));
      this.assignChild('.errors', DialogErrorsView, { model : this.model });
      
      return this;
    },

    onCancel : function () {
      window.location.href = '/view';
    }
  });

  var MergeTokenView = RegisterTokenView.extend({
    className : 'auth-form merge-token',

    templateName : 'merge-token',

    templateData : function () {
      return {
        email : this.model.get('source_identity').split(':')[1]
      };
    }
  });  
  
  var MergeSuccessView = DialogBaseView.extend({
    className : 'auth-form merge-success',
    
    templateName : 'merge-success',
    
    render : function () {
      this.$el.html(this.template()({ 
        target : this.model.get('identity_key'), 
        source : this.model.get('source_identity').split(':')[1]
      }));

      return this;
    },

    onSubmit : function () {
      window.location.href = '/view';
    }
  });

  var AuthSpacerView = ViewfinderView.extend({
    className : 'spacer',

    initialize: function () {
      this.bindResize(this.onResize);
    },

    render : function () {
      this.onResize();
      return this;
    },

    onResize : function () {
      var $w = $(window);
      var winWidth = $w.width();
      var winHeight = $w.height();

      this.$el.css('height', winHeight);

      // Set photo image size.
      photoImageSize = winWidth > 480 ? 'full' : 'med';
    }
  });
  
  
  // AUTHENTICATION MASTER VIEW
  // **************************
  var AuthenticationView = namespace.AuthenticationView = ViewfinderView.extend({
    initialize : function () {
      this.bindModel('change:mode', this.render);
    },
    
    viewMap : {
      'login_begin' : LoginBeginView,
      'login_success' : LoginSuccessView,
      'register_begin' : RegisterBeginView,
      'register_token' : RegisterTokenView,
      'register_success' : RegisterSuccessView,
      'reset_begin' : ResetBeginView,
      'reset_token' : ResetTokenView,
      'reset_password' : ResetPasswordView,
      'reset_success' : ResetSuccessView,
      'reset_success_merge' : ResetSuccessMergeView,
      'merge_begin' : MergeBeginView,
      'merge_confirm' : MergeConfirmView,
      'merge_token' : MergeTokenView,
      'merge_success' : MergeSuccessView
    },
    
    render : function () {
      this.destroyChildren();
      this.appendChild(AuthSpacerView);

      var mode = this.model.get('mode');
      var view = this.viewMap[mode];
      if (view) {
        this.appendChild(view, {model : this.model});
      }
      
      return this;
    }
  });
  
  
  // **********************************************************************************************
  //                                          ROUTER
  // **********************************************************************************************
  var ViewfinderRouter = Backbone.Router.extend({
    routes : {
      "conv/:viewpoint(/:photo)" : "selectionRoute",
      "inbox" : "inboxRoute",
      "settings" : "settingsRoute",
      "*path" : "defaultRoute"
    },
    
    initialize : function (options) {
      this.selection = options.selection;
      this.settings = options.settings;
      this.viewpoint_id = null;
      this.photo_id = null;
      this.settings.on('change:page', this.onChangePage, this);
      this.selection.on('change:viewpoint', this.onViewpointChange, this);
      this.selection.on('change:photo', this.onPhotoChange, this);
    },
    
    // Called when the selection is being updated via a new URL route.
    selectionRoute : function (viewpoint_id, photo_id) {
      this.settings.page(null);

      this.viewpoint_id = viewpoint_id;
      this.photo_id = photo_id;
      
      var router = this;
      var scope = this.selection.scope();
      
      // Create a placeholder viewpoint if the requested viewpoint doesn't already exist.  This gives
      // us a good target for hooking up events, even if the user doesn't actually have access to the
      // viewpoint with the given id or it hasn't loaded yet.
      var viewpoint = scope.viewpoints.getPlaceholder(viewpoint_id);
      this.selection.viewpoint(viewpoint);
      
      function selectPhoto () {
        if (router.viewpoint_id !== viewpoint_id || 
          router.photo_id !== photo_id) {
          // Disregard this is selection has changed while waiting for episode/photo to load.
          return;
        }
        
        if (!photo_id) {
          router.selection.activity(null);
          return;
        }
        
        var photo = scope.photos.get(photo_id);
        var activity = photo ? viewpoint.findActivity(photo) : null;
        router.selection.activity(activity);
        router.selection.photo(photo);
      }
      
      // If the viewpoint is already loaded, we can go ahead and attempt to select the photo.  Otherwise,
      // wait until the viewpoint is loaded (the selection of the viewpoint will trigger its loading).
      if (viewpoint.loaded() || photo_id === null) {
        selectPhoto();
      } else {
        router.listenToOnce(viewpoint, 'change:loaded', selectPhoto);
      }
    },

    inboxRoute : function () {
      this.settings.page(null);
      this.viewpoint_id = null;
      this.selection.viewpoint(null);
    },

    settingsRoute : function () {
      this.settings.page('settings');
    },

    defaultRoute : function () {
      // Adds the #inbox fragment so that the back button can work properly.
      this._setUrl(true);
    },
    
    // Called whenever the selected viewpoint is changed.
    onViewpointChange : function () {
      // Compare the currently selected viewpoint to the viewpoint_id the router currently thinks is selected.
      // If they are different, the the selection changed outside of the router and we have to update the URL.
      var viewpoint = this.selection.viewpoint();
      var update = false;
      if (viewpoint) {
        update = viewpoint.id !== this.viewpoint_id;
      } else {
        update = this.viewpoint_id !== null;
      }

      if (update) {
        // Changing viewpoint id implies that photo was deselected.  Always add to history.
        this.viewpoint_id = viewpoint ? viewpoint.id : null;
        this.photo_id = null;
        this._setUrl();
      }  
    },
    
    // Called whenever the selected photo is changed.
    onPhotoChange : function () {
      // Compare the currently selected photo to the photo_id the router currently thinks is selected.
      // If they are different, the the selection changed outside of the router and we have to update the URL.
      var photo = this.selection.photo();
      
      if (photo === null) {
        if (this.photo_id !== null) {
          // Indicates a return to conversation view from single image view.  Always add to
          // history.
          this.photo_id = null;
          this._setUrl();
        }
        return;
      }
      
      var update = photo.id !== this.photo_id;

      if (update) {
        // If the previous photo_id was null, we are entering single image view and should thus leave a new entry
        // in the router's history.  
        //
        // If the previous photo was not null, then this is a lateral change between different images in single image 
        // view and we upated the URL without adding an entry to the history.
        var replace = this.photo_id !== null;
        this.photo_id = photo.id;
        this._setUrl(replace);
      }
    },
    
    _setUrl : function (replace) {
      replace = replace || false;
      var url;
      if (this.settings.page()) {
        url = 'settings';
      } else if (this.viewpoint_id) {
        url = 'conv/' + this.viewpoint_id;
        if (this.photo_id !== null) {
          url += '/' + this.photo_id;
        }
      } else {
        url = 'inbox';
      }
      
      this.navigate(url, {replace : replace});
    },
   
    onChangePage : function () {
      this._setUrl();
    }
  });
  
  // **********************************************************************************************
  //                                 APPLICATION VIEW
  // **********************************************************************************************
  
  var ProspectiveSignupView = DialogBaseView.extend({
    className : 'auth-form prospective-signup',
    
    templateName : 'prospective-signup',

    initialize : function(options) {
      this.settings = options.settings;
    },

    render : function () {
      var identity, identity_type;
      if (viewfinder.own_user.email) {
        identity = viewfinder.own_user.email;
        identity_type = 'e-mail address';
      } else {
        identity = viewfinder.own_user.phone;
        identity_type = 'phone number';
      }

      this.$el.html(this.template()({
        id : identity,
        id_type : identity_type
      }));
      this.delegateEvents();
      return this;
    },

    onSubmit : function () {
      window.location.href = '/auth';
    },

    onCancel : function () {
      window.location.href = '/auth#merge';
    },

    subOption : function () {
      this.settings.dialog(null);
    }
  });

  var DialogOverlayView = ViewfinderView.extend({
    events : {
      'click .auth-form' : 'stopClick',
      'click' : 'close'
    },

    viewMap : {
      'prospective-signup' : ProspectiveSignupView      
    },

    initialize : function (options) {
      this.settings = options.settings;
      this.listenTo(this.settings, 'change:dialog', this.render);

      if (!viewfinder.fx.fixed) {
        this.$el.addClass('nofixed');
        this.bindScroll(this.adjustWindow);
        this.bindResize(this.adjustWindow);
        this.adjustWindow();
      }
    },

    render : function () {
      this.destroyChildren();
      if (this.settings.dialog()) {
        this.$el.css('display', 'block');
        this.appendChild(AuthSpacerView);
        var view = this.viewMap[this.settings.dialog()];
        if (view) {
          this.appendChild(view, {settings : this.settings});
        }
      } else {
        this.$el.css('display', 'none');
      }
    },

    adjustWindow : function () {
      var $w = $(window);
      var h = window.innerHeight;
      var top = $w.scrollTop();
      this.$el.css({
        height : h,
        top : top
      });
    },

    stopClick : function (e) {
      e.stopPropagation();
    },

    close : function () {
      this.settings.dialog(null);
    }
  });

  var DropdownMenuView = namespace.DropdownMenuView = ViewfinderView.extend({
    events : {
      'click .dropdown' : 'suppressClick',
      'click' : 'toggleMenu'
    },

    templateName : 'dropdown-menu',

    initialize : function () {
      this.bindDom('document', 'click', this.closeMenu);
      this.open = false;
    },

    render : function () {
      this.$el.html(this.template()());
      this.delegateEvents();
    },

    suppressClick : function (e) {
      e.stopPropagation();
    },

    toggleMenu : function (e) {
      this.open = !this.open;
      this.$el.toggleClass('open', this.open);
      e.stopPropagation();
    },
    
    closeMenu : function() {
      this.open = false;
      this.$el.removeClass('open');
    }
  });

  var HeaderBackButtonView = ViewfinderView.extend({
    events : {
      'click a': 'onClick'
    },

    templateName : 'header-back',

    initialize : function (options) {
      this.settings = this.options.settings;
      this.viewpoints = options.viewpoints;
      this.listenTo(this.viewpoints, 'add change:update_seq change:viewed_seq', this.render);
    },

    render : function () {
      var inboxCount = viewfinder.flags.isRegistered ? 
            this.viewpoints.unviewedCount() : 
            this.viewpoints.models.length;
      this.$el.html(this.template()({
        justBack : this.settings.page(),
        inboxCount : inboxCount
      }));
    
      this.delegateEvents();
    },

    onClick : function () {
      if (this.settings.page()){
        this.settings.page(null);
      } else if (this.model.viewpoint()) {
        this.model.viewpoint(null);
      }
    }
  });

  var HeaderView = namespace.HeaderView = ViewfinderView.extend({
    events : {
      'click .to-top' : 'backToTop'
    },

    initialize : function (options) {
      this.settings = this.options.settings;
      this.$el.addClass(viewfinder.flags.isRegistered ? 'registered' : 'unregistered');

      this.bindLayoutChange(this.render);
      this.bindModel('change:viewpoint', this.render);
      this.listenTo(this.settings, 'change:page', this.render);
    },

    render : function () {
      this.destroyChildren();
      var layout = layoutManager.layout();
      this['render' + layout]();

      this.assignChild('.back', HeaderBackButtonView, {
        model : this.model,
        viewpoints : this.model.scope().viewpoints, 
        settings : this.settings
      });

      this.delegateEvents();
      return this;
    },

    renderMobile : function () {
      this.$el.html(this.template('header-mobile')());
    },

    renderOneCol : function () {
      this.$el.html(this.template('header-one-col')());
    },

    renderTwoCol : function () {
      this.$el.html(this.template('header-two-col')());
    },

    backToTop : function () {
      $('html, body').animate({ scrollTop : 0 }, 200);
    }
  });

  var SettingsView = namespace.SettingsView = ViewfinderView.extend({
    initialize : function () {
      this.bindLayoutChange(this.render);
    },

    render : function (layout) {
      this.destroyChildren();
      layout = layoutManager.layout();
      this['render' + layout]();
      this.delegateEvents();
    },

    renderMobile : function () {
      this.$el.html(this.template('settings-one-col')());
    },

    renderOneCol : function () {
      this.$el.html(this.template('settings-one-col')());
    },

    renderTwoCol : function () {
      this.$el.html(this.template('settings-two-col')());
    }  
  });

  var SettingsManager = Backbone.Model.extend({
    defaults : {
      page : null,
      dialog : null
    },

    page : function (newPage) {
      if (_.isUndefined(newPage)) {
        return this.get('page');
      }

      this.set('page', newPage);
      return newPage;
    },

    dialog : function (newDialog) {
      if (_.isUndefined(newDialog)) {
        return this.get('dialog');
      }

      this.set('dialog', newDialog);
      return newDialog;
    }
  });

  // The main application view - constructs an instance of the data models and populates them from the
  // viewfinder query service.  While this view ends up driving the model to a degree, all other child
  // views are driven directly from the model.
  //
  // This class contains aspects of both a Controller and a View from a MVC framework.  It is actually
  // more like a Presenter from a Model-View-Presenter framework.  So, no need to obsess over the purity
  // here - this is the best place to put this code.
  var AppView = namespace.AppView = ViewfinderView.extend({
    events : {
      'click #inbox .prospective' : 'signupDialog',
      'click #conversation .signup-cta' : 'signupDialog',
      'click .cta-button' : 'signupDialog'
    },
    
    initialize: function() {
      var app = this;

      // Attach all collections in a new scope directly to the AppView.
      var scope = viewfinder.models.createViewfinderScope();

      // Prepopulate scope with own user info.
      scope.users.add(viewfinder.own_user);

      _.extend(this, scope);
      var selection = this.selection;
      this.settings = new SettingsManager();
      
      this.bindResize(this.onResize);
      
      // Create base views and append them to the page.
      var $conv = $('#conversation');
      var convView = SelectedConversationView.create({model : this.selection, el : $conv}, this);
      convView.render();

      var $inbox = $('#inbox');
      if (viewfinder.flags.enableInbox) {
        var inboxView = InboxView.create({collection : this.viewpoints, 
                                          network : this.network,
                                          el : $inbox}, 
                                         this);  
        inboxView.render();
      }

      var $settings = $('#settings');
      var settingsView = SettingsView.create({model : this.settings, el : $settings}, this);
      settingsView.render();
      
      var $gall = $('#gallery');
      var galleryView = GalleryView.create({model : this.selection, el : $gall}, this);
      galleryView.render();

      var $head = $('#header');
      var headerView = HeaderView.create({model : selection, settings : this.settings, el : $head}, this);
      headerView.render();

      var $dialog = $('#dialog');
      var dialogView = DialogOverlayView.create({settings : this.settings, el : $dialog}, this);
      dialogView.render();
     
      // Set up effects.
      $conv.scrollEffect({bufferBottom: 600, bufferTop: 500, useWindow : true});
      $inbox.scrollEffect({bufferBottom: 300, useWindow : true});

      $inbox.addClass('show');

      var selectPage = function () {
        app.$('.page').removeClass('show');
        if (app.settings.page()) {
          $settings.addClass('show');
        } else if (selection.viewpoint()) {
          $conv.addClass('show');
        } else {
          $inbox.addClass('show');
          var previous = selection.previous('viewpoint');
          if (previous) {
            _.defer(function () {
              previous.trigger('ui:locate');
            });
          }
        }

        $(window).trigger('resize');
      };

      this.settings.on('change:page', selectPage);
      selection.on('change:viewpoint',  selectPage);

      // Set up router.
      var router = new ViewfinderRouter({selection : selection, settings : this.settings});
      Backbone.history.start(); 
  
      // Set up notification polling along with active callbacks to detect an idle user.
      var poll = new viewfinder.models.NotificationPoller(this.network);
      var activeCb = _.bind(poll.userAction, poll);
      var $d = $(document);
      $d.mousemove(activeCb);
      $d.keypress(activeCb);

      this.network.startQueryFollowed();
      
      // Registered user sessions are able to query for notifications, thus updating live.
      // Prospective users start at the conversation associated with the link they clicked,
      // not the inbox.
      if (viewfinder.flags.isRegistered) {
        this.network.getLastNotification();
        this.network.onIdle(_.bind(poll.start, poll));
        layoutManager.on('resetPolling', poll.reset, poll);
      } else if (viewfinder.viewpoint_id && this.selection.viewpoint() === null) {
        var vp = this.viewpoints.getPlaceholder(viewfinder.viewpoint_id);
        this.selection.viewpoint(vp);
      }

      if (viewfinder.fx.fastclick) {
        FastClick.attach(document.body);
      }

      this.onResize();
      this.delegateEvents();
    },
    
    render : function() {
      return this;
    },
    
    signupDialog : function () {
      this.settings.dialog('prospective-signup');
    },

    signup : function () {
      window.location.href = '/auth';
    },
    
    onResize : function() {
      // I cannot find a way to do this with CSS that does not mess up vertical scrolling.
      // The minimum height is necessary in order to ensure that the left and write drawers
      // are always completely covered, even by a short conversation.
      var $w = $(window);
      this.$el.css('min-height', $w.height());
      
      // Adjust the size of images loaded when displaying conversations.
      photoImageSize = $w.width() > 480 ? 'full' : 'med';
    }
  });
  
  
})(jQuery, viewfinder.views);
