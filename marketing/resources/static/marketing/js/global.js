var g_nViewportWid = $(window).width();
var g_nViewportHei = $(window).height();
var g_nBreakpointWid = parseInt($("#css_vp_wid").css("width"), 10);
//var g_nScrollTop = $(window).scrollTop();
//var g_nScrollBot = g_nScrollTop + g_nViewportHei;


var g_xVF = {
	debug:0,
	homepage_slides: [
		"/static/marketing/images/pemberton_viewFinder.coHero5.jpg", 
		"/static/marketing/images/V1-1_Website_HeroImage_2.png", 
		"/static/marketing/images/pemberton_viewFinder.coHero1.jpg", 
		"/static/marketing/images/V1-1_Website_HeroImage_1.png", 
		"/static/marketing/images/pemberton_viewFinder.coHero3.jpg"
	],
	homepage_slideshow_playing: false,
	current_homepage_slide: 0,
	tour_player: false,
	current_tour_video: 1,
  has_html5_video: Modernizr.video && !Modernizr.touch,
  dial_player: false,
  dial_played: false,
	current_page: "",
	tour_convo_data: {
		current_phone_index:null,
		positions: []
	},

	

	init: function(){
		_eventAdd("resize", this.onResize, this);
		_eventAdd("scroll", this.onScroll, this);

		var self = this;
    self.current_page = $("body").attr("data-current-page");

		if(self.current_page=="homepage"){
			self.initHomepage();
			self.initTour();
		}

		else if(self.current_page=="faq"){
			self.initFaq();
		}


		$(window).resize(function(){
			_eventFire("resize");
		});

		setTimeout(function(){
			_eventFire("resize");
		},1);

		$(window).scroll(function(){
			_eventFire("scroll");
		});

		_eventFire("scroll");		
	},
	
	initHomepage: function(){
		var self = this;
		
    if(self.has_html5_video){
      $("#dial_panel").addClass("has_video");
      videojs("dial_bkgd_video").ready(function(){
        self.dial_player = this;
        self.dial_player.volume(0);
      });
      /*
       videojs("tour_video").ready(function(){
       self.tour_player = this;
       self.tour_player.volume(0);
       self.tour_player.on("ended", function(){
       _eventFire("play_tour_video", { num:++self.current_tour_video });
       });
       });
       */
    }
    else {
      $("#dial_bkgd_video").remove();
      //$("#tour_video").remove();
    }
		self.current_homepage_slide = Math.floor(Math.random()*self.homepage_slides.length);
		//self.homepage_slides.shuffle();

		self.startHomepageSlideshow();		
	},
	
	initFaq: function(){

		$(".faq-toc").on("click", "li a", function(e){
			e.preventDefault();
			var toc_num = $(this).parent().index();
			var faq_pos = $(".faq-list li.faq-item").eq(toc_num).offset().top;
			location.href = '#'+(toc_num+1);
			$("html, body").animate({"scrollTop" : faq_pos });
		});
		if(window.location.hash){
			var hash = parseInt(location.hash.substr(1));
			if(!isNaN(hash)) {
				var toc_num = Math.max(0, hash-1);
				$(".faq-toc li.faq-item").eq(toc_num).find("a").trigger("click");
			}
		}				
	},

	initTour: function(){
		var tour_intro = $("#tour_intro_panel");
		var self = this; 
					
		var convo_panel = $("#conversation_panel");		
	},
	
	tourIntroOpen: function(side, animate){
		var self = this;
		var tour_intro = $("#tour_intro_panel");
		
		if(self.tourIntroSliding) return;
		

		var tour_phone_inbox = $(".tour_iphone_inbox");
		var tour_phone_library = $(".tour_iphone_library");
		var detail_inbox = tour_intro.find(".detail_inbox");
		var detail_library = tour_intro.find(".detail_library");
		var tour_intro_copy = tour_intro.find(".intro_copy");
		var tour_intro_frame = tour_intro.find(".content_frame");

		self.tourIntroSliding = true;
		tour_intro.addClass("focused");

		if(g_nBreakpointWid <= 1000){

			//tour_intro.animate({ "height":"1000px" }, 1000, "easeInOutQuart");
		}
		else {
			tour_intro.find(".intro_copy").css({ "position":"absolute", "width":tour_intro_copy.width()+"px","top":tour_intro_copy.position().top+"px","left":tour_intro_copy.position().left+"px" });//.fadeOut(400);
			
			if(animate){
				tour_intro.find(".caption_holder").fadeOut(400);
				tour_intro.animate({ "padding-bottom":"60px" }, 1000, "easeInOutQuart");
			}
			else {
				tour_intro.find(".caption_holder").hide();
				tour_intro.css({ "padding-bottom":"60px" });
			}
		}

		// inbox click (right)	
		if(side=="inbox"){
			if(g_nBreakpointWid <= 600){
				var detail_inbox_top = (tour_intro_frame.find(".divider").position().top + tour_intro_frame.find(".divider").height()) + 50 + 430 + 44; // margin-top + height (.tour_iphone_library)
				if(animate){
					tour_phone_inbox.find(".caption_holder").animate({ top:"10px", opacity:0 }, 800, "easeInOutQuart");
					detail_inbox.show().css({ opacity:0 });
					detail_inbox.animate({ top:detail_inbox_top+"px", opacity:1 }, 1000, "easeInOutQuart", function(){
						self.tourIntroSliding = false;					
					});
					tour_phone_inbox.animate({ "margin-top":(tour_intro.find(".detail_inbox").height()+44)+"px", "padding-top":0, height:"570px" }, 800, "easeInOutQuart");

					tour_phone_library.animate({ "margin-top":"50px", "padding-top":"180px", height:"430px" }, 800, "easeInOutQuart");
					tour_intro.find(".tour_iphone_library .caption_holder").animate({ top:0, opacity:1 }, 800, "easeInOutQuart");
					detail_library.fadeOut(400);
				}
				else {
					tour_phone_inbox.find(".caption_holder").css({ top:"10px", opacity:0 });
					detail_inbox.show().css({ top:detail_inbox_top+"px", opacity:1 });
					self.tourIntroSliding = false;					
					tour_phone_inbox.css({ "margin-top":(tour_intro.find(".detail_inbox").height()+44)+"px", "padding-top":0, height:"570px" });
					tour_phone_library.css({ "margin-top":"50px", "padding-top":"180px", height:"430px" });
					tour_phone_library.find(".caption_holder").css({ top:0, opacity:1 });
					detail_library.hide();
				}
			}
			else if(g_nBreakpointWid <= 1000){
				var detail_inbox_right = tour_intro_frame.width()+ 40 - tour_intro.find(".detail_inbox").width();
				if((tour_phone_library.offset().left) < 0){
					detail_inbox_right = (tour_intro_frame.offset().left + tour_intro_frame.width()) - tour_intro.find(".detail_inbox").width() - 40;
				}
				if(animate){
					tour_phone_inbox.animate({ "margin-top":"0px" }, 800, "easeInOutQuart");
					tour_phone_inbox.find(".caption_holder").animate({ "top":"250px" }, 800, "easeInOutQuart");
					tour_phone_library.delay(300).animate({ "margin-top":"550px" }, 1000, "easeInOutQuart");
					tour_phone_library.find(".caption_holder").delay(300).animate({ "top":"270px" }, 1000, "easeInOutQuart");
					detail_library.animate({ left:"-60px", opacity:0 }, 800, "easeInOutQuart", function(){
						$(this).hide();
						self.tourIntroSliding = false;								
					});
					detail_inbox.show().delay(300).animate({ right:detail_inbox_right+"px", opacity:1 }, 1000, "easeInOutQuart");
				}
				else {
					tour_phone_inbox.css({ "margin-top":"0px" });
					tour_phone_inbox.find(".caption_holder").css({ "top":"250px" });
					tour_phone_library.css({ "margin-top":"550px" });
					tour_phone_library.find(".caption_holder").css({ "top":"270px" });
					detail_library.css({ left:"-60px", opacity:0 }).hide();
					self.tourIntroSliding = false;								
					detail_inbox.show().css({ right:detail_inbox_right+"px", opacity:1 });
				}

			}
			else {
				var inbox_right_margin = tour_intro.find(".content_frame").width() - ( tour_intro.find(".content_frame").width()*0.15) - tour_intro.find(".tour_iphone_inbox").width();
				if(animate){
					tour_phone_library.delay(200).animate({ "margin-left":"-260px" }, 1000, "easeInOutQuart");
					tour_phone_inbox.delay(350).animate({ "margin-right":Math.round(inbox_right_margin)+"px" }, {
						duration:1000,
						easing:"easeInOutQuart",
						step: function(now, tween){
							self.tourIntroMotionStep();
						},
						complete: function(){
							self.tourIntroSliding = false;								
						}
					});
				}
				else {
					tour_phone_library.css({ "margin-left":"-260px" });
					tour_phone_inbox.css({ "margin-right":Math.round(inbox_right_margin)+"px" });
					tour_intro_copy.find(".copy_mask").css({ left:"auto", right:0, width:tour_intro_copy.width()+"px" });
					self.tourIntroMotionStep();
					self.tourIntroSliding = false;								
				}
			}

		}
		// library click (left)
		else {
			if(g_nBreakpointWid <= 600){
				var detail_library_top = tour_intro_frame.find(".divider").position().top + tour_intro_frame.find(".divider").height() + 40;
				if(animate){
					tour_phone_library.find(".caption_holder").animate({ top:"10px", opacity:0 }, 800, "easeInOutQuart");
					detail_library.show().css({ opacity:0 });
					detail_library.animate({ top:detail_library_top+"px", opacity:1 }, 1000, "easeInOutQuart", function(){
						self.tourIntroSliding = false;					
					});
					tour_phone_library.animate({ "margin-top":(tour_intro.find(".detail_library").height()+44)+"px", "padding-top":0, height:"570px" }, 800, "easeInOutQuart");
					tour_phone_inbox.animate({ "margin-top":"50px", "padding-top":"180px", height:"430px" }, 800, "easeInOutQuart");
					tour_phone_inbox.find(".caption_holder").animate({ top:0, opacity:1 }, 800, "easeInOutQuart");
					detail_inbox.fadeOut(400);
				}
				else {
					tour_phone_library.find(".caption_holder").css({ top:"10px", opacity:0 });
					detail_library.show().css({ top:detail_library_top+"px", opacity:1 });
					self.tourIntroSliding = false;					
					tour_phone_library.css({ "margin-top":(tour_intro.find(".detail_library").height()+44)+"px", "padding-top":0, height:"570px" });
					tour_phone_inbox.css({ "margin-top":"50px", "padding-top":"180px", height:"430px" });
					tour_phone_inbox.find(".caption_holder").css({ top:0, opacity:1 });
					detail_inbox.hide();
				}
			}
			else if(g_nBreakpointWid <= 1000){
				var detail_library_left = (tour_phone_inbox.offset().left - tour_intro_frame.offset().left) + 40;
				if((tour_phone_library.offset().left) < 0){
					detail_library_left = (tour_intro_frame.offset().left + tour_intro_frame.width()) - detail_library.width() - 40;
				}
				if(animate){
					tour_phone_library.animate({ "margin-top":"0px" }, 800, "easeInOutQuart");
					tour_phone_library.find(".caption_holder").animate({ "top":"250px" }, 800, "easeInOutQuart");
					tour_phone_inbox.delay(300).animate({ "margin-top":"550px" }, 1000, "easeInOutQuart");
					tour_phone_inbox.find(".caption_holder").delay(300).animate({ "top":"270px" }, 1000, "easeInOutQuart");
					detail_inbox.animate({ right:"-60px", opacity:0 }, 800, "easeInOutQuart", function(){
						$(this).hide();
						self.tourIntroSliding = false;								
					});
					detail_library.show().delay(300).animate({ left:detail_library_left+"px", opacity:1 }, 1000, "easeInOutQuart");
				}
				else {
					tour_phone_library.css({ "margin-top":"0px" });
					tour_phone_library.find(".caption_holder").css({ "top":"250px" });
					tour_phone_inbox.css({ "margin-top":"550px" });
					tour_phone_inbox.find(".caption_holder").css({ "top":"270px" });
					detail_inbox.css({ right:"-60px", opacity:0 }).hide();
					self.tourIntroSliding = false;								
					detail_library.show().css({ left:detail_library_left+"px", opacity:1 });
				}
			}
			else {
				var inbox_right_margin = (tour_intro.find(".content_frame").width()*0.85) - tour_intro.find(".tour_iphone_inbox").width();
				if(animate){
					tour_phone_inbox.delay(200).animate({ "margin-right":"-260px" }, 1000, "easeInOutQuart");
					tour_phone_library.delay(350).animate({ "margin-left":inbox_right_margin+"px" }, {
						duration:1000, 
						easing: "easeInOutQuart", 
						step:function(){
							self.tourIntroMotionStep();
						},
						complete: function(){
							self.tourIntroSliding = false;								
						}
					});
				}
				else {
					tour_phone_inbox.css({ "margin-right":"-260px" });
					tour_phone_library.css({ "margin-left":inbox_right_margin+"px" });
					tour_intro_copy.find(".copy_mask").css({ left:0, right:'auto', width:tour_intro_copy.width()+"px" });
					self.tourIntroMotionStep();
					self.tourIntroSliding = false;								
				}
			}					
		}

		if(g_nBreakpointWid > 1000 && animate){
			$("html, body").stop(true).animate({scrollTop: tour_intro.offset().top }, 1000, 'easeInOutQuint');
		}

		tour_intro.find(".iphone_holder").not($(".tour_iphone_"+side)).removeClass("disabled");
		$(".tour_iphone_"+side).addClass("disabled");

	},
	
	tourIntroClose: function(){
		var self = this;
		var tour_intro = $("#tour_intro_panel");

		self.tourIntroSliding = true;
		tour_intro.find(".iphone_holder").removeClass("disabled");
		
		if(g_nBreakpointWid <= 600){
			tour_intro.find(".iphone_holder").animate({ "margin-top":"50px", "padding-top":"180px", height:"430px" }, 800, "easeInOutQuart");
			tour_intro.find(".iphone_holder .caption_holder").animate({ top:0, opacity:1 }, 800, "easeInOutQuart", function(){
				self.tourIntroSliding = false;					
			});
			tour_intro.find(".detail_holder").fadeOut(400);
		}

		else if(g_nBreakpointWid <= 1000){
			tour_intro.find(".detail_inbox").animate({ right:"-60px", opacity:0 }, 800, "easeInOutQuart");
			tour_intro.find(".tour_iphone_inbox").delay(200).animate({ "margin-top":"250px" }, 800, "easeInOutQuart");
			tour_intro.find(".tour_iphone_inbox .caption_holder").delay(200).animate({ "top":"-10px" }, 800, "easeInOutQuart");

			tour_intro.find(".detail_library").animate({ left:"-60px", opacity:0 }, 800, "easeInOutQuart");
			tour_intro.find(".tour_iphone_library").delay(200).animate({ "margin-top":"250px" }, 800, "easeInOutQuart");
			tour_intro.find(".tour_iphone_library .caption_holder").delay(200).animate({ "top":"-10px" }, 800, "easeInOutQuart", function(){
				self.tourIntroSliding = false;	
				_eventFire("resize");
			});

		}
		else {
			tour_intro.find(".tour_iphone_library").animate({ "margin-left":"-75px" }, {
				duration:1000, 
				easing: "easeInOutQuart", 
				step:function(){
					self.tourIntroMotionStep();
				}
			});

			tour_intro.find(".tour_iphone_inbox").animate({ "margin-right":"-75px" }, {
				duration:1000, 
				easing: "easeInOutQuart", 
				step:function(){
					//self.tourIntroMotionStep();
				}
			});
			tour_intro.animate({ "padding-bottom":"300px" }, 1000, 'easeInOutQuint', function(){
				self.tourStartMagnetism = true;
				self.tourIntroSliding = false;	
				//$(this).removeAttr("style");
				_eventFire("resize");				
			});
			tour_intro.find(".caption_holder").fadeIn(400);				
		}		
	},
	
	
	tourConvoSlidePhone: function(ind, animate){
		var self = this;
		if(self.tourConvoSliding) return;
		//if(self.tour_convo_data.current_phone_index==ind) return;
		
		var convo_panel = $("#conversation_panel");
		var convo_phone_list = convo_panel.find(".phone_list");
		var convo_phones = convo_panel.find(".phone_list li");
		
		var dir = (ind > self.tour_convo_data.current_phone_index || (ind==0 && self.tour_convo_data.current_phone_index==convo_phones.length-1)) ? "left":"right";
		if(self.tour_convo_data.current_phone_index==0 && ind==convo_phones.length-1) dir = "right";
		self.tour_convo_data.current_phone_index = ind;

		// radio active states
		convo_panel.find(".convo_nav_list li.radio").removeClass("current");
		convo_panel.find(".convo_nav_list li.radio").eq(ind).addClass("current");
		
		var current_caption = convo_panel.find(".caption .copy.current");
		var goto_caption = $("#convo_caption"+ind);//convo_panel.find(".caption .copy.current").eq(ind);
		goto_caption.addClass("current");
		
		// set current class to phone
		convo_phones.removeClass("current");
		var convo_focused_phone = $("#convo_phone"+ind); 
		convo_focused_phone.addClass("current");
		var focused_phone_ind = convo_phones.index(convo_focused_phone);

		// set position index 
		convo_phones.each(function(i, el){
			$(el).attr("data-prev-index", $(el).attr("data-index"));
			
			if(i > focused_phone_ind) {
				if(focused_phone_ind==0 && i==convo_phones.length-1) $(el).attr("data-index", 0);
				else $(el).attr("data-index", (convo_phones.index($(el)) - focused_phone_ind)+1);
			}
			if(i < focused_phone_ind){
				if(i==focused_phone_ind-1) $(el).attr("data-index", 0);
				else $(el).attr("data-index", ((convo_phones.length - focused_phone_ind) + convo_phones.index($(el)))+1);
			}
		});
		
		convo_focused_phone.attr("data-index", 1);
		
		current_caption.hide();
		goto_caption.show();
		
		if(g_nBreakpointWid > 600 && g_nBreakpointWid <= 1000){
			convo_phones.hide();
			$("#convo_phone"+ind).show();
		}
		else {

			convo_phones.each(function(i, el){
				var pos_ind = parseInt($(el).attr("data-index"));
				var pos_prev_ind = parseInt($(el).attr("data-prev-index"));
				var pos_left = self.tour_convo_data.positions[pos_ind];
				
				if(!animate){
					$(el).css({ left:pos_left+"px" });
					return;
				}
				self.tourConvoSliding = true;
				
				var off_screen_left = convo_panel.find(".phone_list").offset().left + 382;
				var off_screen_right = g_nViewportWid-convo_panel.find(".phone_list").offset().left;
				
				// slide first left, loop
				if(dir=="left" && pos_prev_ind < pos_ind){ //(pos_prev_ind==0 && pos_ind==convo_phones.length-1) || ){
					$(el).stop(true).animate({ left:-off_screen_left+"px" }, 400, 'easeInOutQuint', function(){
						$(this).css({ left:off_screen_right+"px" }).animate({ left:pos_left+"px" }, 300, 'easeOutQuint');
						self.tourConvoSliding = false;
					});
				}
				// slide last right, loop
				else if(dir=="right" && pos_prev_ind > pos_ind){ //pos_prev_ind==convo_phones.length-1 && pos_ind==0){
					$(el).stop(true).animate({ left:off_screen_right+"px" }, 400, 'easeInOutQuint', function(){
						$(this).css({ left:-off_screen_left+"px" }).animate({ left:pos_left+"px" }, 300, 'easeOutQuint');
						self.tourConvoSliding = false;
					});					
				}
				else { 
					// slide left, then loop
					var params = {
						duration:500, 
						easing:'easeInOutQuint',
						complete: function(){
							self.tourConvoSliding = false;						
						}
					};
					$(el).stop(true).animate({ left:pos_left+"px" }, params);
				}
				
			});
			
		}
	},
	
	tourIntroMotionStep: function(){
		var tour_intro = $("#tour_intro_panel");
		var tour_intro_copy = tour_intro.find(".intro_copy");
		var tour_intro_copy_mask = tour_intro.find(".intro_copy .copy_mask");
		tour_intro.find(".detail_holder").css({ 'display':'inline' });

		var detail_holder_inbox = tour_intro.find(".detail_inbox");
		var tour_iphone_inbox = tour_intro.find(".tour_iphone_inbox");
		var tour_iphone_inbox_left = tour_iphone_inbox.offset().left;
		var tour_iphone_inbox_right = tour_iphone_inbox.offset().left + tour_iphone_inbox.width();
		
		var detail_holder_library = tour_intro.find(".detail_library");
		var tour_iphone_library = tour_intro.find(".tour_iphone_library");
		var tour_iphone_library_left = tour_iphone_library.offset().left;
		var tour_iphone_library_right = tour_iphone_library.offset().left + tour_iphone_library.width();

		var copy_mask_wid = 0;
		var detail_library_mask_wid = detail_holder_library.width();
		var detail_inbox_mask_wid = detail_holder_inbox.width();

		if(tour_iphone_library_right > tour_intro_copy.offset().left){
			copy_mask_wid = (tour_iphone_library_left - tour_intro_copy_mask.offset().left) + 63;
			tour_intro_copy_mask.css({ left:0, right:'auto', width:copy_mask_wid+"px" });
		}
		if(tour_iphone_inbox_left < (tour_intro_copy.offset().left+tour_intro_copy.width())){
			copy_mask_wid = (tour_intro_copy_mask.offset().left + tour_intro_copy_mask.width()) - tour_iphone_inbox_left -33;
			tour_intro_copy_mask.css({ left:"auto", right:0, width:copy_mask_wid+"px" });
		}
		
		if(tour_iphone_library_left+33 > detail_holder_library.offset().left){
			detail_library_mask_wid = detail_holder_library.width() - ((tour_iphone_library_left+33) - detail_holder_library.offset().left);
			detail_holder_library.css({ opacity:1 });
		}
		else detail_holder_library.css({ opacity:0 });
		
		detail_holder_library.find(".detail_mask").css({ width:detail_library_mask_wid+"px" });
		
		if(tour_iphone_inbox_right < detail_holder_inbox.offset().left+detail_holder_inbox.width()){
			detail_inbox_mask_wid = (tour_iphone_inbox_left + tour_iphone_inbox.width()) - detail_holder_inbox.offset().left-33;
			detail_holder_inbox.css({ opacity:1 });
		}
		else detail_holder_inbox.css({ opacity:0 });
		
		detail_holder_inbox.find(".detail_mask").css({ width:detail_inbox_mask_wid+"px" });
		

	},
	
	tourOpenWatchVideoOverlay: function(){
		var self = this;
		self.youtube_player_loaded = false;
		
		$("#dial_video_holder").html(self.youtube_video_embed);
		
		demo_video = new YT.Player('dial_video_iframe', {
			height: '315',
			width: '560',
			videoId: '1IH6FZlzTRY',
			playerVars: { 'autoplay': 0 },
			events: {
				'onReady': function(e){
					self.youtube_player_loaded = true;
					if(self.youtube_start_video_onload){
						demo_video.playVideo();
					}
				},
				'onStateChange': function (e){
					if(e.data==0){
						self.tourCloseWatchVideoOverlay();
					}
				}
			}
		});
		
		$("#tour_video_overlay").fadeIn(500);
		
		self.adjustDialVideoPos();
		if(!Modernizr.touch) {
			if(demo_video && self.youtube_player_loaded) {
				demo_video.playVideo();
			}
			else self.youtube_start_video_onload = true;
		}
	},
	
	tourCloseWatchVideoOverlay: function(){
		var self = this;
		$("#tour_video_overlay").fadeOut(500, function(){
			self.youtube_player_loaded = false;
			self.youtube_start_video_onload = false;
			$("#dial_video_iframe").remove();
		});
		if(demo_video) {
			demo_video.pauseVideo();
			demo_video.destroy();
		}
	},
	
	startHomepageSlideshow: function(){
		var self = this;
		
		self.homepage_slideshow_playing = true;
		self.current_homepage_slide++;
		if(self.current_homepage_slide >= self.homepage_slides.length){
			self.current_homepage_slide = 0;
		}
		var next_img = self.homepage_slides[self.current_homepage_slide];

		$("#home_hero .bkgd_img_off").css({ "background-image":"url("+next_img+")" }).fadeIn(1000, function(){
			$(this).removeClass("bkgd_img_off").addClass("bkgd_img");
		});
		$("#home_hero .bkgd_img").fadeOut(1000, function(){
			$(this).removeClass("bkgd_img").addClass("bkgd_img_off");

			$("#animate_ref").animate({ opacity:1 }, 5000, function(){
				$(this).css({ opacity:0 });
				self.startHomepageSlideshow();
			});
		});

	},

	pauseHomepageSlideshow: function(){
		var self = this;
		self.homepage_slideshow_playing = false;
		$("#animate_ref").stop();
	},

	adjustDialVideoPos: function(){
		var viewport_ratio = g_nViewportWid/g_nViewportHei;
		var video_ratio = $("#dial_video_holder").attr("data-ratio");
		
		var video_wid = g_nViewportWid-25;
		var video_hei = video_wid/video_ratio;
		
		if(viewport_ratio > video_ratio){
			video_hei = g_nViewportHei-25;
			video_wid = video_hei * video_ratio;
		}
		$("#dial_video_holder").css({ "width":video_wid+"px", "height":video_hei+"px" });
		$("#dial_video_holder iframe").attr("width", video_wid).attr("height", video_hei);
		
		var video_top = Math.max(0, (g_nViewportHei - video_hei)/2);
		var video_left = Math.max(0, (g_nViewportWid - video_wid)/2);
		
		$("#dial_video_holder").css({ 'margin-top':video_top+"px", "margin-left":video_left+"px" });
		
	},
	
	onExpandDialVideo: function(e, params){
		if($("#dial_panel").hasClass("expanded")) return;
		
		//$.address.state("/video/");
		var self = e.data;

		var panel = $("#dial_panel");
		panel.find(".bkgd_img").fadeOut(400);
		panel.find(".content_frame").fadeOut(400);
		panel.animate({ height:g_nViewportHei+"px", "backgroundColor":"#000" }, 1000, 'easeInOutQuint', function(){
			self.adjustDialVideoPos();
			
			panel.addClass("expanded").find(".close").fadeIn(400);
			$("#dial_video_holder").fadeIn(400);
			
			if(demo_video && !Modernizr.touch) demo_video.playVideo();
		});
		
		$("html, body").stop(true).animate({scrollTop: $("#dial_panel").offset().top }, 1000, 'easeInOutQuint');
		
	},
	
	onCollapseDialVideo: function(e, params){
		var panel = $("#dial_panel");
		var orig_height = panel.find(".bkgd_img").height();

		if(demo_video) demo_video.pauseVideo();

		panel.find(".close").fadeOut(400);
		$("#dial_video_holder").fadeOut(400);
		panel.animate({ height:orig_height+"px" }, 1000, 'easeInOutQuint', function(){
			panel.removeClass("expanded");
			panel.removeAttr("style");
		});
		panel.find(".content_frame").delay(700).fadeIn(400);
		panel.find(".bkgd_img").delay(700).fadeIn(400);
		
		$("html, body").stop(true).animate({scrollTop: ($("#dial_panel").offset().top - 50) }, 1000, 'easeInOutQuint');
		
	},
	
	onPlayTourVideo: function(e, params){
		var self = e.data;
		
		self.current_tour_video = params.num;
		
		//if(!self.tour_player) return;
		if(self.current_tour_video > 3) self.current_tour_video = 1;
		
		
		$("#tour_points .tour_point").removeClass("current");
		$("#tour_video_holder").removeClass("point_1 point_2 point_3");

		var vid_mp4 = "/static/marketing/video/FILE0059_converted.mp4";
		var vid_webm = "/static/marketing/video/FILE0059.webm";
		var vid_ogg = "/static/marketing/video/FILE0059.ogv";
		
		if(self.current_tour_video==1){
			vid_mp4 = "/static/marketing/video/FILE0063_converted.mp4";
			vid_webm = "/static/marketing/video/FILE0063.webm";
			vid_ogg = "/static/marketing/video/FILE0063.ogv";
			
			$("#tour_video_holder").addClass("point_1");
			$(".tour_point_1").addClass("current");
		}
		else if(self.current_tour_video==2){
			vid_mp4 = "/static/marketing/video/FILE0022_converted.mp4";
			vid_webm = "/static/marketing/video/FILE0022.webm";
			vid_ogg = "/static/marketing/video/FILE0022.ogv";
				
			$("#tour_video_holder").addClass("point_2");
			$(".tour_point_2").addClass("current");
		}
		else {
			$("#tour_video_holder").addClass("point_3");
			$(".tour_point_3").addClass("current");
		}

		/*
		if(self.has_html5_video && !self.tour_player){
			self.tour_player.src([
				{ type: "video/mp4", src: vid_mp4 },
				{ type: "video/webm", src: vid_webm },
				{ type: "video/ogg", src: vid_ogg }
			]).play();
		}
		*/
	},
	
	onResize: function(e, params){
		var self = e.data;
		
		g_nViewportWid = $(window).width();
		g_nViewportHei = $(window).height();
		g_nBreakpointWid = self.getBreakpointWid();
		
		if(self.debug)
			$("#debug").html(g_nViewportWid+" ("+g_nBreakpointWid+") x "+g_nViewportHei).show();

		if(self.current_page=="homepage"){
			self.resizeHomepage(e);
      self.resizeTour(e);
		}
	},
	
	resizeHomepage:function(e){
		
		var self = e.data;
		
		$("#download_panel .download").addClass("large");

		if(g_nBreakpointWid <= 1100){
			if(g_nBreakpointWid <= 600){
					$("#download_panel .download").removeClass("large");
			}
      if(self.has_html5_video){
        if(self.dial_player) self.dial_player.dimensions(924,373);
        //if(self.tour_player) self.tour_player.dimensions(201,357);
      }
		}
    else {
      if(self.has_html5_video){
        if(self.dial_player) self.dial_player.dimensions(1200,484);
        //if(self.tour_player) self.tour_player.dimensions(268,476);
      }
    }

    ("#dial_bkgd_video video").attr("width", "100%");

		if($("#dial_panel").hasClass("expanded")){
			$("#dial_panel").css({ "height":g_nViewportHei+"px" });
			self.adjustDialVideoPos();
		}
	},
	
	resizeTour:function(e){
		
		var self = e.data;
		
		var convo_panel = $("#conversation_panel");
		var phone_list = $("#conversation_panel .phone_list");
		var tour_panel = $("#tour_intro_panel");
		var tour_panel_intro_copy = tour_panel.find(".intro_copy");
		
		//phone_list.find(".phone3").removeAttr("style");
		//tour_panel_intro_copy.removeAttr("style");
		$(".resize_clear").removeAttr("style");
		$(".imgwid_100").removeAttr("height").attr("width", "100%");
		
		//tour_panel.find(".iphone_holder").removeClass("disabled");
		//tour_panel.removeClass("focused");


		if(g_nBreakpointWid <= 600){
			var detail_left = (tour_panel.find(".content_frame").width() - tour_panel.find(".detail_holder").width())/2;
			tour_panel.find(".detail_holder").css({ left:detail_left+"px" });
			
			var max_copy_hei = 0;
			convo_panel.find(".caption .copy").each(function(i, el){
				max_copy_hei = Math.max(max_copy_hei, $(el).show().height());
				$(el).hide();
			});
			convo_panel.find(".caption").css({ height:max_copy_hei+"px" });


			var convo_panel_frame_wid = convo_panel.width();
			var convo_panel_phone_wid = phone_list.find("li").eq(0).width();
			self.tour_convo_data.positions = new Array();
			self.tour_convo_data.positions[1] = (convo_panel_frame_wid - convo_panel_phone_wid)/2;
			self.tour_convo_data.positions[0] = self.tour_convo_data.positions[1] - convo_panel_phone_wid - 22;
			self.tour_convo_data.positions[2] = self.tour_convo_data.positions[1] + convo_panel_phone_wid + 22;
			self.tour_convo_data.positions[3] = self.tour_convo_data.positions[2] + convo_panel_phone_wid + 22;
			self.tour_convo_data.positions[4] = self.tour_convo_data.positions[3] + convo_panel_phone_wid + 22;
			for(var p in self.tour_convo_data.positions){
				phone_list.find(".phone"+p).css({ "left":(self.tour_convo_data.positions[p])+"px" });
			}
		}
		else if(g_nBreakpointWid <= 1000){
			var intro_phones_wid = (tour_panel.find(".tour_iphone_inbox").offset().left + tour_panel.find(".tour_iphone_inbox").width()) - tour_panel.find(".tour_iphone_library").offset().left;
			if(g_nViewportWid < intro_phones_wid){
				var width_diff = (intro_phones_wid - g_nViewportWid)/2;
				tour_panel.find(".tour_iphone_library .caption_holder").css({ "left":width_diff+"px" });
				tour_panel.find(".tour_iphone_inbox .caption_holder").css({ "right":width_diff+"px" });
			}
		}
		else {
			// tour intro
			// freeze intro_copy #magnetism
			tour_panel_intro_copy.css({ left:((tour_panel.find(".content_frame").width() - tour_panel_intro_copy.width())/2)+"px" });
			
			// conversation positioning
			var convo_panel_frame_wid = convo_panel.find(".content_frame").width();
			self.tour_convo_data.positions = new Array();
			self.tour_convo_data.positions[0] = (-convo_panel_frame_wid*0.15);
			self.tour_convo_data.positions[1] = (convo_panel_frame_wid*0.55);
			self.tour_convo_data.positions[2] = Math.max(self.tour_convo_data.positions[1]+370,  (convo_panel_frame_wid*0.85));
			self.tour_convo_data.positions[3] = Math.max(self.tour_convo_data.positions[2]+370,  (convo_panel_frame_wid*1.15));
			self.tour_convo_data.positions[4] = Math.max(self.tour_convo_data.positions[3]+370,  (convo_panel_frame_wid*1.45));
			for(var p in self.tour_convo_data.positions){
				phone_list.find(".phone"+p).css({ "left":(self.tour_convo_data.positions[p])+"px" });
			}
		}
		
		var current_convo_ind = 0;
		if(phone_list.find("li.current").length > 0)
			current_convo_ind = phone_list.find("li").index(phone_list.find("li.current"));
		self.tourConvoSlidePhone(current_convo_ind, false);

		if(tour_panel.find(".iphone_holder.disabled").length > 0){
			var side = "library";
			if(tour_panel.find(".iphone_holder.disabled").hasClass("tour_iphone_inbox")) 
				side = "inbox";
			
			self.tourIntroOpen(side, false);
		}

		// set some helper data vars
		/*
		tour_panel.find(".iphone_holder").each(function(i, el){
			$(el).attr("data-off-x", $(el).position().left).attr("data-off-y", $(el).position().top);
		});
		*/

	},	
	
	
	onScroll: function(e, params){
		g_nScrollTop = $(window).scrollTop();
		g_nScrollBot = g_nScrollTop + g_nViewportHei;

		var self = e.data;

		if(self.current_page=="homepage"){
			if(($("#dial_panel").offset().top+$("#dial_panel").height()) < g_nScrollBot) {
				if(self.dial_player && !self.dial_played){
					self.dial_played = true;
					self.dial_player.play();
				}
			}

			// stop hero slideshow if off page
			if($("#home_hero").in_viewport()){
				if(!self.homepage_slideshow_playing)
					self.startHomepageSlideshow();
			}
			else {
				self.pauseHomepageSlideshow();
			}

			// stop tour video if off page
			if(self.has_html5_video){
				/*
				if($("#tour_video_holder").in_viewport()){
					if(self.tour_player.paused()){
						self.tour_player.play();
					}
				}
				else {
					self.tour_player.pause();
				}
				*/
			}
		}
		
	},
	
	getBreakpointWid: function(){
		return parseInt($("#css_vp_wid").css("width"), 10);		
	}
	
};





