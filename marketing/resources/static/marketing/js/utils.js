function isNumber(n) {
  return !isNaN(parseFloat(n)) && isFinite(n);
}

function cleanupFormatting_blockquote(sel){
	return;
	var text = $(sel).html();
	text = text.replace("<blockquote>", '<div class="blockquote_holder"><blockquote>');
	text = text.replace("</blockquote>", '</blockquote></div>');
	$(sel).html(text);
}

function getQsParamByName(name){
  name = name.replace(/[\[]/, "\\\[").replace(/[\]]/, "\\\]");
  var regexS = "[\\?&]" + name + "=([^&#]*)";
  var regex = new RegExp(regexS);
  var results = regex.exec(window.location.search);
  if(results == null)
    return "";
  else
    return decodeURIComponent(results[1].replace(/\+/g, " "));
}


function vimeo_responsive(){
	$(".vimeo_aspect").each(function(i, el){
		var aspect = $(el).attr("data-aspect");
		var new_hei = $(el).width()/aspect;
		$(el).css({ height:new_hei+"px" });
	});
}


function _eventAdd(event_name, handler, event_data){
	$(document).bind(event_name, event_data, handler);
}

function _eventFire(event_name, param){
	if(!param) param = null;
	$(document).triggerHandler(event_name, param);
}

