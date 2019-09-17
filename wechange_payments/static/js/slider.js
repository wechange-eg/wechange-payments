$(function() {
	
	var update_slider = function (event, ui) {
	      
		// set the values on slide
		$(".payment-slider #value").val(ui.value);
		
		// slide the background gradient
		var color = $('.payment-slider #slider').css('color');
		var bg_color = $('.payment-slider #slider .background').css('background-color');
		var max = $('.payment-slider #slider').slider("option", "max");
		var min = $('.payment-slider #slider').slider("option", "min");
		var percentage = (100 * (ui.value - min) / (max - min)).toFixed();
		var style = [
			"background: @slider-main-color",
			"background: -moz-linear-gradient(left, " + color + " " + percentage + "%, " + bg_color + " " + percentage + "%)",
			"background: -webkit-linear-gradient(left," + color + " " + percentage + "%, " + bg_color + " " + percentage + "%)",
			"background: linear-gradient(to right, " + color + " " + percentage + "%, " + bg_color + " " + percentage + "%)",
			"filter: progid:DXImageTransform.Microsoft.gradient( startColorstr='" + color + "', endColorstr='" + bg_color + "',GradientType=1 )",
		].join(';');
		$('.payment-slider #slider').attr('style', style);
		
		// Show Different Elements based on values
		$('.payment-slider .donation-outcome').hide();
		if (ui.value < 5) {
			$('.payment-slider .low-amount').show();
		} else if (ui.value < 10) {
			$('.payment-slider .medium-amount').show();
		} else {
			$('.payment-slider .high-amount').show();
		}
		
		// toggle disabled status from submit buttons if they have class .enabled-on-change and the amount changed
		if (!ui.initial) {
			var $submitButton = $('.payment-slider').closest('form').find('button[type=submit].enabled-on-change');
			if (PAYMENTS_SLIDER_INITIAL_PAYMENT_AMOUNT != ui.value) {
				$submitButton.removeAttr('disabled').removeClass('disabled');
			} else {
				$submitButton.attr('disabled', 'disabled').addClass('disabled');
			}
		}
	};

    $slider = $('.payment-slider #slider');
    $slider.slider({
	    value: PAYMENTS_SLIDER_INITIAL_PAYMENT_AMOUNT,
	    min: PAYMENTS_MINIMUM_PAYMENT_AMOUNT,
	    max: PAYMENTS_MAXIMUM_PAYMENT_AMOUNT,
	    step: 1,
	    slide: update_slider,
    });
    
    $('.slider-container #value').on('change keyup', function(){
    	$slider.slider('value', this.value);
    	$slider.slider('option', 'slide')(null, { value: this.value })
    }).on('focus', function(){
    	this.select();
    });
    $('.amount-frame').on('click', function(){
    	$('.slider-container #value').focus();
    })
    
    // on initial, trigger slide event to update visuals
    $slider.slider('option', 'slide')(null, { value: $slider.slider('value'), initial: true });
    
    
});

