window.PaymentForm = {
	registerPaymentForm: function () {
		// register submits 
		$('body').on('submit', 'form', window.PaymentForm.handleFormSubmit);
		
		// make hidden fields not required
		var makeRequired = function(name, value){
    		$('.conditional-select-container[data-select-name="' + name + '"] input').each(function(){
    			this.setAttribute ("required", "false");
    		});
    		$('.conditional-select-container[data-select-name="' + name + '"][data-select-value="' + value + '"] input').each(function(){
    			this.setAttribute ("required", "true");
    		});
    	};
		// onchange trigger
    	$('.conditional-select select').on('change', function() {
    		makeRequired(this.name, this.value);
		});
    	// initial state
    	$('.conditional-select select').each(function(){
    		makeRequired(this.name, this.value);
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
			if (responseJSON && 'missing_parameters' in responseJSON) {
				$.each(responseJSON['missing_parameters'], function(index, name) {
					$form.find('[name="' + name +'"]').addClass('missing');
				});
			} 
			// display error
			$form.find('.error-frame').show().find('.error-message').text(error);
			// re-enable form
	        $form.removeClass('disabled');
	        $form.find('input,textarea,select,button').removeAttr('disabled');
	        // scroll up
	        window.scrollTo(0, 0);
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
	
}


$(function() {
	window.PaymentForm.registerPaymentForm();
});
