window.PaymentForm = {
	registerPaymentForm: function () {
		// register submits 
		$('body').on('submit', 'form', window.PaymentForm.handleFormSubmit);
		
		// make fields inside conditional-select-containers not required if they aren't selected
		var makeRequired = function(name, value){
    		$('.conditional-select-container[data-select-name="' + name + '"] input').each(function(){
    			this.removeAttribute("required");
    		});
    		$('.conditional-select-container[data-select-name="' + name + '"][data-select-value="' + value + '"] input').each(function(){
    			this.setAttribute("required", "true");
    		});
    	};
		// onchange trigger for conditional-select
    	$('.conditional-select select').on('change', function() {
    		makeRequired(this.name, this.value);
		});
    	// initial state for conditional-select
    	$('.conditional-select select').each(function(){
    		makeRequired(this.name, this.value);
    	});
    	
    	// step-specific triggers
    	$('a[data-toggle="tab"]').on('shown.bs.tab', function (e) {
    		// every step: make fields with inside containers with "data-only-required-step" only required if we're on that step
		    var step = $(e.target).attr("href") // activated tab
		    $('[data-only-required-step] input').each(function(){
    			this.removeAttribute("required");
    		});
    		$('[data-only-required-step="' + step + '"] input').each(function(){
    			this.setAttribute("required", "true");
    		});
    	});
    	
    	// step3: payment information: check if form is valid, and if not, trigger an early validation
    	$('.to-step4-button').on('click', function(){
			var $form = $('#payments-form');
			if ($form[0].checkValidity()) {
				// generate the payment summary
				window.PaymentForm.generatePaymentSummary();
				// go to step 4
				$('.hidden-step-4-button').click();
			} else {
				// fake-trigger a submit to trigger the native validation popup
				$('<input type="submit">').hide().appendTo($form).click().remove();
			}
    	});
	},
	
	handleFormSubmit: function (event) { 
		event.preventDefault();  // prevent form from submitting
        var $form = $(this);
        
        // serialize and disable form (serialization must be done before disabling)
		var data = $form.serializeArray();
		data.push({'name': 'ajax_form_id', 'value': $form.attr('id')});
        $form.addClass('disabled');
        $form.find('input,textarea,select,button').attr('disabled', 'disabled').removeClass('missing');
    	$form.find('.error-frame').hide();
        
    	window.PaymentForm.submitForm($form, data).then(function(data){
    		window.PaymentForm.handleSuccess(data);
		}).catch(function(responseJSON){
			var error = "An unknown error occured!";
			if (responseJSON && 'error' in responseJSON) {
				error = responseJSON['error'];
			}
			$form.find('[name]').removeClass('missing');
			if (responseJSON && 'missing_parameters' in responseJSON) {
				$.each(responseJSON['missing_parameters'], function(index, name) {
					$form.find('[name="' + name +'"]').addClass('missing');
				});
			}
			
			// display error messages on fields
			$form.find('.field-error-message').remove();
			$form.find('[name]').removeClass('error');
			if (responseJSON && 'field_errors' in responseJSON) {
				$.each(responseJSON['field_errors'], function(name, errorMessage) {
					$form.find('[name="' + name +'"]').addClass('error').after(
						'<span class="field-error-message">' + errorMessage + '</span>'
					);
				});
			}
			// display error
			$form.find('.error-frame').show().find('.error-message').text(error);
			// re-enable form
	        $form.removeClass('disabled');
	        $form.find('input,textarea,select,button').removeAttr('disabled');
	        // scroll up
	        window.scrollTo(0, 0);
	        // show step 3
	        $('a[data-toggle="tab"][href="#step3"]').click();
		});
    }, 
	
	submitForm: function ($form, data) {
		return new Promise(function(resolve, reject) {
			$.ajax({
			  url: $form.attr("action"),
			  type: 'POST',
			  data: data, 
			  success: function (response, textStatus, xhr) {
	              if (xhr.status == 200) {
	              	resolve(response);
	              } else {
	              	reject(xhr.statusText);
	              }
	          },
	          error: function (xhr, textStatus) {
	          	  reject(xhr.responseJSON);
	          },
			});
		});
	},
	
	handleSuccess: function (data) {
		if ('redirect_to' in data) {
			window.location.href = data['redirect_to']
		} else {
			alert('success! but no "redirect_to" in return data, so NYI what to do here.')
			console.log(data)
		}
	},
	
	generatePaymentSummary: function (data) {
		var $form = $('#payments-form');
		var summaryContainer = $('.payment-summary');
		var summary_fields = [
			'amount',
			'account_holder',
			'iban',
			'bic',
			'first_name',
			'last_name',
			'address',
			'postal_code',
			'city',
			'country',
		];
		// fill placeholders with data from the form
		$.each(summary_fields, function(idx, fieldname) {
			var value = $form.find('input[name="' + fieldname + '"],select[name="' + fieldname + '"]').val();
			summaryContainer.find('[data-summary-item="' + fieldname + '"]').text(value);
		});
		// show payment type items based on chosen type
		var payment_type = $form.find('select[name="payment_type"]').val();
		summaryContainer.find('[data-summary-payment-type]').hide();
		summaryContainer.find('[data-summary-payment-type="' + payment_type + '"]').show();
	},
}


$(function() {
	window.PaymentForm.registerPaymentForm();
	
	$('.focus-slider-onclick').click(function(){
		setTimeout(function(){$('.slider-container #value').focus()}, 200);
	});
});
