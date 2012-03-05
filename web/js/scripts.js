	$(function(){
		$('.powered-by img, .xmpp').popover();
		
		$('#accordian').collapse({
			toggle: false
		});
		
		$('#donate').click(function(){
			$('#donate').submit();
		});
	
		// fix sub nav on scroll
		var $win = $(window)
		  , $nav = $('.subnav')
		  , navTop = $('.subnav').length && $('.subnav').offset().top - 40
		  , isFixed = 0
	
		processScroll()
	
		$win.on('scroll', processScroll)
	
		function processScroll() {
		  var i, scrollTop = $win.scrollTop()
		  if (scrollTop >= navTop && !isFixed) {
			isFixed = 1
			$nav.addClass('subnav-fixed')
		  } else if (scrollTop <= navTop && isFixed) {
			isFixed = 0
			$nav.removeClass('subnav-fixed')
		  }
		}

	
		
		$('.powered-by img, .xmpp').popover();

	});
