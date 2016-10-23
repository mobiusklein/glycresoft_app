var GlycanCompositionLCMSSearchController, GlycanCompositionLCMSSearchPaginator, GlycanCompositionLCMSSearchTabView, viewGlycanCompositionPeakGroupingDatabaseSearchResults,
  bind = function(fn, me){ return function(){ return fn.apply(me, arguments); }; },
  extend = function(child, parent) { for (var key in parent) { if (hasProp.call(parent, key)) child[key] = parent[key]; } function ctor() { this.constructor = child; } ctor.prototype = parent.prototype; child.prototype = new ctor(); child.__super__ = parent.prototype; return child; },
  hasProp = {}.hasOwnProperty;

GlycanCompositionLCMSSearchPaginator = (function(superClass) {
  extend(GlycanCompositionLCMSSearchPaginator, superClass);

  GlycanCompositionLCMSSearchPaginator.prototype.pageUrl = "/view_glycan_lcms_analysis/{analysisId}/page/{page}";

  GlycanCompositionLCMSSearchPaginator.prototype.tableSelector = ".glycan-chromatogram-table";

  GlycanCompositionLCMSSearchPaginator.prototype.tableContainerSelector = "#chromatograms-table";

  GlycanCompositionLCMSSearchPaginator.prototype.rowSelector = '.glycan-match-row';

  function GlycanCompositionLCMSSearchPaginator(analysisId, handle1, controller) {
    this.analysisId = analysisId;
    this.handle = handle1;
    this.controller = controller;
    this.rowClickHandler = bind(this.rowClickHandler, this);
    GlycanCompositionLCMSSearchPaginator.__super__.constructor.call(this, 1);
  }

  GlycanCompositionLCMSSearchPaginator.prototype.getPageUrl = function(page) {
    if (page == null) {
      page = 1;
    }
    return this.pageUrl.format({
      "page": page,
      "analysisId": this.analysisId
    });
  };

  GlycanCompositionLCMSSearchPaginator.prototype.rowClickHandler = function(row) {
    return this.controller.showGlycanCompositionDetailsModal(row);
  };

  return GlycanCompositionLCMSSearchPaginator;

})(PaginationBase);

GlycanCompositionLCMSSearchTabView = (function(superClass) {
  extend(GlycanCompositionLCMSSearchTabView, superClass);

  GlycanCompositionLCMSSearchTabView.prototype.tabSelector = 'ul.tabs';

  GlycanCompositionLCMSSearchTabView.prototype.tabList = ["chromatograms-plot", "chromatograms-table", "summary-abundance-plot"];

  GlycanCompositionLCMSSearchTabView.prototype.defaultTab = "chromatograms-plot";

  GlycanCompositionLCMSSearchTabView.prototype.updateUrl = '/view_glycan_lcms_analysis/{analysisId}/content';

  GlycanCompositionLCMSSearchTabView.prototype.containerSelector = '#glycan-lcms-container';

  function GlycanCompositionLCMSSearchTabView(analysisId, handle1, parent1, updateHandlers) {
    var parent;
    this.analysisId = analysisId;
    this.handle = handle1;
    this.parent = parent1;
    parent = this.parent;
    GlycanCompositionLCMSSearchTabView.__super__.constructor.call(this, updateHandlers);
  }

  GlycanCompositionLCMSSearchTabView.prototype.getUpdateUrl = function() {
    return this.updateUrl.format({
      'analysisId': this.analysisId
    });
  };

  return GlycanCompositionLCMSSearchTabView;

})(TabViewBase);

GlycanCompositionLCMSSearchController = (function() {
  GlycanCompositionLCMSSearchController.prototype.containerSelector = '#glycan-lcms-container';

  GlycanCompositionLCMSSearchController.prototype.glycanTableSelector = ".glycan-chromatogram-table";

  GlycanCompositionLCMSSearchController.prototype.detailModalSelector = '#glycan-detail-modal';

  GlycanCompositionLCMSSearchController.prototype.detailUrl = "/view_glycan_lcms_analysis/{analysisId}/details_for/{chromatogramId}";

  function GlycanCompositionLCMSSearchController(analysisId) {
    var updateHandlers;
    this.analysisId = analysisId;
    this.handle = $(this.containerSelector);
    this.currentPage = 1;
    this.glycanTable = $(this.glycanTableSelector);
    this.glycanDetailsModal = $(this.detailModalSelector);
    this.paginator = new GlycanCompositionLCMSSearchPaginator(this.analysisId, this.handle, this);
    updateHandlers = [
      (function(_this) {
        return function() {
          console.log("Running update handler 1");
          return _this.paginator.setupTable();
        };
      })(this), (function(_this) {
        return function() {
          var handle;
          console.log("Running update handler 2");
          handle = $(_this.tabView.containerSelector);
          $.get("/view_glycan_lcms_analysis/" + _this.analysisId + "/chromatograms_chart").success(function(payload) {
            console.log("Chromatograms Retrieved");
            return handle.find("#chromatograms-plot").html(payload);
          });
          return $.get("/view_glycan_lcms_analysis/" + _this.analysisId + "/abundance_bar_chart").success(function(payload) {
            console.log("Bar Chart Retrieved");
            return handle.find("#summary-abundance-plot").html(payload);
          });
        };
      })(this)
    ];
    this.tabView = new GlycanCompositionLCMSSearchTabView(this.analysisId, this.handle, this, updateHandlers);
  }

  GlycanCompositionLCMSSearchController.prototype.updateView = function() {
    console.log("updateView");
    return this.tabView.updateView();
  };

  GlycanCompositionLCMSSearchController.prototype.showGlycanCompositionDetailsModal = function(row) {
    var handle, id, modal, url;
    handle = $(row);
    id = handle.attr('data-target');
    modal = this.getModal();
    url = this.detailUrl.format({
      analysisId: this.analysisId,
      chromatogramId: id
    });
    return $.get(url).success(function(doc) {
      modal.find('.modal-content').html(doc);
      $(".lean-overlay").remove();
      return modal.openModal();
    });
  };

  GlycanCompositionLCMSSearchController.prototype.getModal = function() {
    return $(this.detailModalSelector);
  };

  GlycanCompositionLCMSSearchController.prototype.unload = function() {
    return GlycReSoft.removeCurrentLayer();
  };

  return GlycanCompositionLCMSSearchController;

})();

viewGlycanCompositionPeakGroupingDatabaseSearchResults = function() {
  var currentPage, downloadCSV, glycanDetailsModal, glycanTable, setup, showGlycanCompositionDetailsModal, unload, updateView;
  glycanDetailsModal = void 0;
  glycanTable = void 0;
  currentPage = 1;
  setup = function() {
    updateView();
    return $("#save-csv-file").click(downloadCSV);
  };
  updateView = function() {
    var handle;
    handle = $(this);
    $("#content-container").html("<div class=\"progress\"><div class=\"indeterminate\"></div></div>").fadeIn();
    return GlycReSoft.ajaxWithContext('/view_database_search_results/results_view/').success(function(doc) {
      var tabs;
      $('#content-container').hide();
      $('#content-container').html(doc).fadeIn();
      tabs = $('ul.tabs');
      tabs.tabs();
      if (GlycReSoft.context['view-active-tab'] !== void 0) {
        console.log(GlycReSoft.context['view-active-tab']);
        $('ul.tabs').tabs('select_tab', GlycReSoft.context['view-active-tab']);
      } else {
        $('ul.tabs').tabs('select_tab', 'glycome-overview');
      }
      $('.indicator').addClass('indigo');
      $('ul.tabs .tab a').click(function() {
        return GlycReSoft.context['view-active-tab'] = $(this).attr('href').slice(1);
      });
      glycanDetailsModal = $('#glycan-detail-modal');
      glycanTable = $("#glycan-table");
      return updateGlycanCompositionTablePage(1);
    }).error(function(error) {
      return console.log(arguments);
    });
  };
  showGlycanCompositionDetailsModal = function() {
    var handle, id;
    handle = $(this);
    id = handle.attr('data-target');
    console.log(id);
    return PartialSource.glycanCompositionDetailsModal({
      "id": id
    }, function(doc) {
      glycanDetailsModal.find('.modal-content').html(doc);
      $(".lean-overlay").remove();
      return glycanDetailsModal.openModal();
    });
  };
  unload = function() {
    return GlycReSoft.removeCurrentLayer();
  };
  downloadCSV = function() {
    var handle, id;
    handle = $(this);
    id = handle.attr('data-target');
    return $.ajax("/view_database_search_results/export_csv/" + id, {
      data: JSON.stringify({
        "context": GlycReSoft.context,
        "settings": GlycReSoft.settings
      }),
      contentType: "application/json",
      type: 'POST'
    });
  };
  return setup();
};

//# sourceMappingURL=view-glycan-composition-peak-group-database-search.js.map
