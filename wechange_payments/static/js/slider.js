$(function() {

	var update_debit_amount = function (event) {
		var amount = $(".payment-slider #value").val();
		var debit_period = $(".period-slider #value").val();
		var debit_months = PAYMENTS_DEBIT_PERIOD_MONTHS[debit_period];
		var debit_sum = amount * debit_months;
		var debit_period_display = PAYMENTS_DEBIT_PERIODS[debit_period];
		var display = debit_sum + " € " + debit_period_display;
		$(".period-slider #display").text(display);
	};

	var update_amount_slider = function (event, ui) {
		var selectAll = false;

		// for invalid values, jump back to default value and select input box
		if (!$.isNumeric(ui.value)) {
			ui.value = PAYMENTS_SLIDER_INITIAL_MONTHLY_AMOUNT;
			selectAll = true;
		} else if (ui.value > PAYMENTS_MAXIMUM_ALLOWED_MONTHLY_AMOUNT || ui.value < PAYMENTS_MINIMUM_MONTHLY_AMOUNT) {
			selectAll = true;
		}
		// cap at real allowed value
		ui.value = Math.max(PAYMENTS_MINIMUM_MONTHLY_AMOUNT, Math.min(ui.value, PAYMENTS_MAXIMUM_ALLOWED_MONTHLY_AMOUNT));
		// set the values on slide
		$(".payment-slider #value").val(ui.value);
		$('.payment-slider #slider').slider('value', ui.value)

		if (selectAll) {
			$(".payment-slider #value").focus().select();
		}
		
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
		} else if (ui.value < 15) {
			$('.payment-slider .high-amount').show();
		} else {
			$('.payment-slider .very-high-amount').show();
		}

		$('.payment-slider .max-amount-label').text(Math.max(ui.value, PAYMENTS_MAXIMUM_MONTHLY_AMOUNT) + ' €');

		// toggle disabled status from submit buttons if they have class .enabled-on-change and the amount changed
		if (!ui.initial) {
			var $submitButton = $('.payment-slider').closest('form').find('button[type=submit].enabled-on-change');
			if (PAYMENTS_SLIDER_INITIAL_MONTHLY_AMOUNT != ui.value) {
				$submitButton.removeAttr('disabled').removeClass('disabled');
			} else {
				$submitButton.attr('disabled', 'disabled').addClass('disabled');
			}
		}

		// update the debit amount to the changed monthly amount value
		update_debit_amount();
	};

	$slider = $('.payment-slider #slider');
	$slider.slider({
		value: PAYMENTS_SLIDER_INITIAL_MONTHLY_AMOUNT,
		min: PAYMENTS_MINIMUM_MONTHLY_AMOUNT,
		max: PAYMENTS_MAXIMUM_MONTHLY_AMOUNT,
		step: 1,
		slide: update_amount_slider,
	});

	$('.slider-container #value').on('change keyup', function () {
		$slider.slider('value', this.value);
		$slider.slider('option', 'slide')(null, {value: this.value})
	}).on('click', function () {
		this.select();
	});
	$('.amount-frame').on('click', function () {
		$('.slider-container #value').focus();
	});

	// on initial, trigger slide event to update visuals
	$slider.slider('option', 'slide')(null, {value: $slider.slider('value'), initial: true});
	// initially focus but deselect slider value
	var textInput = $('.slider-container #value').focus();
	// set textbox value again incase it was higher than slider max and has now been reset
	$(".payment-slider #value").val(PAYMENTS_SLIDER_INITIAL_MONTHLY_AMOUNT);

	var update_period_slider = function (event, ui) {
		var selectAll = false;

		// set the value
		$(".period-slider #value").val(PAYMENTS_DEBIT_PERIOD_SLIDER_VALUES[ui.value]);

		// slide the background gradient
		var color = $('.period-slider #slider').css('color');
		var bg_color = $('.period-slider #slider .background').css('background-color');
		var max = $('.period-slider #slider').slider("option", "max");
		var min = $('.period-slider #slider').slider("option", "min");
		var percentage = (100 * (ui.value - min) / (max - min)).toFixed();
		var style = [
			"background: @slider-main-color",
			"background: -moz-linear-gradient(left, " + color + " " + percentage + "%, " + bg_color + " " + percentage + "%)",
			"background: -webkit-linear-gradient(left," + color + " " + percentage + "%, " + bg_color + " " + percentage + "%)",
			"background: linear-gradient(to right, " + color + " " + percentage + "%, " + bg_color + " " + percentage + "%)",
			"filter: progid:DXImageTransform.Microsoft.gradient( startColorstr='" + color + "', endColorstr='" + bg_color + "',GradientType=1 )",
		].join(';');
		$('.period-slider #slider').attr('style', style);

		// update the debit amount to the changed debit period
		update_debit_amount();
	};

	$period_slider = $('.period-slider #slider');
	$period_slider.slider({
		value: PAYMENTS_DEBIT_PERIOD_SLIDER_VALUES.indexOf(PAYMENTS_DEBIT_PERIOD_INITIAL),
		min: 0,
		max: PAYMENTS_DEBIT_PERIOD_SLIDER_VALUES.length - 1,
		step: 1,
		slide: update_period_slider,
	});
	// on initial, trigger slide event to update visuals
	$period_slider.slider('option', 'slide')(null, {value: $period_slider.slider('value'), initial: true});
});
