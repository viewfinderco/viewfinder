// Avoid `console` errors in browsers that lack a console.
(function() {
    var method;
    var noop = function () {};
    var methods = [
        'assert', 'clear', 'count', 'debug', 'dir', 'dirxml', 'error',
        'exception', 'group', 'groupCollapsed', 'groupEnd', 'info', 'log',
        'markTimeline', 'profile', 'profileEnd', 'table', 'time', 'timeEnd',
        'timeStamp', 'trace', 'warn'
    ];
    var length = methods.length;
    var console = (window.console = window.console || {});

    while (length--) {
        method = methods[length];

        // Only stub undefined methods.
        if (!console[method]) {
            console[method] = noop;
        }
    }
}());



Array.prototype.shuffle = function() {
  var i = this.length, j, temp;
  if ( i == 0 ) return this;
  while ( --i ) {
     j = Math.floor( Math.random() * ( i + 1 ) );
     temp = this[i];
     this[i] = this[j];
     this[j] = temp;
  }
  return this;
}




// Place any jQuery/helper plugins in here.
jQuery.browser={};(function(){jQuery.browser.msie=false;
jQuery.browser.version=0;if(navigator.userAgent.match(/MSIE ([0-9]+)\./)){
jQuery.browser.msie=true;jQuery.browser.version=RegExp.$1;}})();


$.fn.input_default = function(param){
    var defaults =
    {
        focus_class: 'focused',
        default_class: 'default'
    };
    var param = $.extend(defaults, param);
		
	$(this).each(function(i, el){
		var _el = $(el);
		if(_el.attr("type").toLowerCase()=="password"){
			_el.addClass("input_type_password");
		}
		_el.focus(function(){
			_el.addClass(param.focus_class);
			_el.removeClass(param.default_class);
			if($.trim(_el.val().toUpperCase())==_el.attr("title").toUpperCase()){
				_el.val('');
				if(_el.hasClass("input_type_password")){
					_el[0].type = "password";
				}
			}
		}).blur(function(){
			_el.removeClass(param.focus_class);
			if($.trim(_el.val())==''){
				if(_el.hasClass("input_type_password")){
					_el[0].type = "text";
				}
				_el.val(_el.attr("title"));
				_el.addClass(param.default_class);
			}
		});

		_el.trigger("blur");
	});
    
    return this;
};



// only tests vertical and includes partial
$.fn.in_viewport = function(param){
	var el_top = $(this).offset().top;
	var el_bot = el_top + $(this).outerHeight();
	
	return !(el_bot < $(window).scrollTop() || el_top > ($(window).scrollTop()+$(window).height()));
};


$.fn.equalize = function(param){
    var defaults = {
		mode: 'height'
    };
    var param = $.extend(defaults, param);
		
	var top_val = 0;
	$(this).each(function(i, el){
		if(param.mode.toLowerCase()=="height")
			top_val = Math.max(top_val, $(el).outerHeight());
		else if(param.mode.toLowerCase()=="width")
			top_val = Math.max(top_val, $(el).outerWidth());
	});
	if(param.mode.toLowerCase()=="height")
		$(this).css({ height:top_val+"px" });
	else if(param.mode.toLowerCase()=="width")
		$(this).css({ width:top_val+"px" });
		
    return this;
};



$.fn.popWindow = function(param){
    var defaults = {};
    var param = $.extend(defaults, param);

	$(this).each(function(i, el){
		var href = $(el).attr("href");
		var params = "status="+($(el).attr("status")?1:0)+",";
		params += "toolbar="+($(el).attr("toolbar")?1:0)+",";
		params += "location="+($(el).attr("location")?1:0)+",";
		params += "menubar="+($(el).attr("menubar")?1:0)+",";
		params += "directories="+($(el).attr("directories")?1:0)+",";
		params += "resizable="+($(el).attr("resizable")?1:0)+",";
		params += "scrollbars="+($(el).attr("scrollbars")?1:0)+",";
		params += "width="+($(el).attr("data-width")?$(el).attr("data-width"):650)+",";
		params += "height="+($(el).attr("data-height")?$(el).attr("data-height"):500);

		$(el).click(function(e){
			e.preventDefault();
			var d = new Date();
			window.open (href,"win_"+d.getTime(),params);
		});

	});
	
    return this;
};


