var ajaxForm, setupAjaxForm;

ajaxForm = function(formHandle, success, error, transform) {
  console.log("Ajaxifying ", formHandle);
  return $(formHandle).on('submit', function(event) {
    var ajaxParams, data, encoding, handle, locked, method, url, wrappedSuccess;
    event.preventDefault();
    console.log(formHandle, "submitting...");
    handle = $(this);
    locked = handle.data("locked");
    if (locked === true) {
      console.log("Form Locked");
      return false;
    } else if (locked === void 0 || locked === null) {
      locked = true;
      handle.data("locked", locked);
    } else if (locked === false) {
      locked = true;
      handle.data("locked", locked);
    }
    console.log("Is form locked", handle.data("locked"));
    if (transform == null) {
      transform = function(form) {
        return new FormData(form);
      };
    }
    url = handle.attr('action');
    method = handle.attr('method');
    data = transform(this);
    encoding = handle.attr('enctype') || 'application/x-www-form-urlencoded; charset=UTF-8';
    wrappedSuccess = function(a, b, c) {
      handle.data("locked", false);
      console.log("Unlocking Form", handle.data("locked"));
      return success(a, b, c);
    };
    ajaxParams = {
      'url': url,
      'method': method,
      'data': data,
      'processData': false,
      'contentType': false,
      'success': wrappedSuccess,
      'error': error
    };
    return $.ajax(ajaxParams);
  });
};

setupAjaxForm = function(sourceUrl, container) {
  var isModal;
  container = $(container);
  isModal = container.hasClass('modal');
  $.get(sourceUrl).success(function(doc) {
    if (isModal) {
      container.find('.modal-content').html(doc);
      container.openModal();
      return container.find('form').submit(function(event) {
        return container.closeModal();
      });
    } else {
      return container.html(doc);
    }
  });
  return container.find('script').each(function(i, tag) {
    var srcURL;
    tag = $(tag);
    srcURL = tag.attr('src');
    if (srcURL !== void 0) {
      return $.getScript(srcURL);
    } else {
      return eval(tag.text());
    }
  });
};

//# sourceMappingURL=ajax-form.js.map
