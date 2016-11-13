var GlycopeptideHypothesisController, GlycopeptideHypothesisPaginator, viewGlycopeptideHypothesis,
  bind = function(fn, me){ return function(){ return fn.apply(me, arguments); }; },
  extend = function(child, parent) { for (var key in parent) { if (hasProp.call(parent, key)) child[key] = parent[key]; } function ctor() { this.constructor = child; } ctor.prototype = parent.prototype; child.prototype = new ctor(); child.__super__ = parent.prototype; return child; },
  hasProp = {}.hasOwnProperty;

GlycopeptideHypothesisPaginator = (function(superClass) {
  extend(GlycopeptideHypothesisPaginator, superClass);

  GlycopeptideHypothesisPaginator.prototype.tableSelector = "#display-table-container";

  GlycopeptideHypothesisPaginator.prototype.tableContainerSelector = "#display-table-container";

  GlycopeptideHypothesisPaginator.prototype.rowSelector = "#display-table-container tbody tr";

  GlycopeptideHypothesisPaginator.prototype.pageUrl = "/view_glycopeptide_hypothesis/{hypothesisId}/{proteinId}/page/{page}";

  function GlycopeptideHypothesisPaginator(hypothesisId1, handle1, controller) {
    this.hypothesisId = hypothesisId1;
    this.handle = handle1;
    this.controller = controller;
    this.rowClickHandler = bind(this.rowClickHandler, this);
    GlycopeptideHypothesisPaginator.__super__.constructor.call(this, 1);
  }

  GlycopeptideHypothesisPaginator.prototype.getPageUrl = function(page) {
    if (page == null) {
      page = 1;
    }
    return this.pageUrl.format({
      "page": page,
      "hypothesisId": this.hypothesisId,
      "proteinId": this.controller.proteinId
    });
  };

  GlycopeptideHypothesisPaginator.prototype.rowClickHandler = function(row) {
    return console.log(row);
  };

  return GlycopeptideHypothesisPaginator;

})(PaginationBase);

GlycopeptideHypothesisController = (function() {
  GlycopeptideHypothesisController.prototype.containerSelector = '#hypothesis-protein-glycopeptide-container';

  GlycopeptideHypothesisController.prototype.proteinTableRowSelector = '.protein-list-table tbody tr';

  GlycopeptideHypothesisController.prototype.proteinContainerSelector = '#protein-container';

  GlycopeptideHypothesisController.prototype.proteinViewUrl = "/view_glycopeptide_hypothesis/{hypothesisId}/{proteinId}/view";

  function GlycopeptideHypothesisController(hypothesisId1, proteinId1) {
    this.hypothesisId = hypothesisId1;
    this.proteinId = proteinId1;
    this.proteinChoiceHandler = bind(this.proteinChoiceHandler, this);
    this.handle = $(this.containerSelector);
    this.paginator = new GlycopeptideHypothesisPaginator(this.hypothesisId, this.handle, this);
    this.setup();
  }

  GlycopeptideHypothesisController.prototype.setup = function() {
    var self;
    self = this;
    $(this.proteinTableRowSelector).click(function(event) {
      return self.proteinChoiceHandler(this);
    });
    return self.proteinChoiceHandler($(this.proteinTableRowSelector)[0]);
  };

  GlycopeptideHypothesisController.prototype.getProteinViewUrl = function(proteinId) {
    return this.proteinViewUrl.format({
      'hypothesisId': this.hypothesisId,
      'proteinId': 'proteinId',
      proteinId: proteinId
    });
  };

  GlycopeptideHypothesisController.prototype.proteinChoiceHandler = function(proteinRow) {
    var handle, id, proteinContainer, url;
    handle = $(proteinRow);
    this.proteinId = id = handle.attr('data-target');
    proteinContainer = $(this.proteinContainerSelector);
    proteinContainer.html("<div class=\"progress\"><div class=\"indeterminate\"></div></div>").fadeIn();
    url = this.getProteinViewUrl(id);
    return GlycReSoft.ajaxWithContext(url).success((function(_this) {
      return function(doc) {
        proteinContainer.hide();
        proteinContainer.html(doc).fadeIn();
        GlycReSoft.context["current_protein"] = id;
        return _this.paginator.setupTable();
      };
    })(this));
  };

  return GlycopeptideHypothesisController;

})();

viewGlycopeptideHypothesis = function(hypothesisId) {
  var currentPage, displayTable, proteinContainer, proteinId, setup, setupGlycopeptideTablePageHandler, updateCompositionTablePage, updateProteinChoice;
  displayTable = void 0;
  currentPage = 1;
  proteinContainer = void 0;
  proteinId = void 0;
  setup = function() {
    proteinContainer = $("#protein-container");
    $('.protein-list-table tbody tr').click(updateProteinChoice);
    return updateProteinChoice.apply($('.protein-list-table tbody tr'));
  };
  setupGlycopeptideTablePageHandler = function(page) {
    if (page == null) {
      page = 1;
    }
    $('.display-table tbody tr').click(function() {});
    $(':not(.disabled) .next-page').click(function() {
      return updateCompositionTablePage(page + 1);
    });
    $(':not(.disabled) .previous-page').click(function() {
      return updateCompositionTablePage(page - 1);
    });
    return $('.pagination li :not(.active)').click(function() {
      var nextPage;
      nextPage = $(this).attr("data-index");
      if (nextPage != null) {
        nextPage = parseInt(nextPage);
        return updateCompositionTablePage(nextPage);
      }
    });
  };
  updateProteinChoice = function() {
    var handle, id, url;
    handle = $(this);
    proteinId = id = handle.attr('data-target');
    proteinContainer.html("<div class=\"progress\"><div class=\"indeterminate\"></div></div>").fadeIn();
    url = "/view_glycopeptide_hypothesis/protein_view/" + proteinId;
    return $.post(url, {
      "settings": GlycReSoft.settings,
      "context": GlycReSoft.context
    }).success(function(doc) {
      proteinContainer.hide();
      proteinContainer.html(doc).fadeIn();
      GlycReSoft.context["current_protein"] = id;
      displayTable = $("#display-table-container");
      return updateCompositionTablePage(1);
    }).error(function(error) {
      return console.log(arguments);
    });
  };
  updateCompositionTablePage = function(page) {
    var url;
    if (page == null) {
      page = 1;
    }
    url = "/view_glycopeptide_hypothesis/protein_view/" + proteinId + "/" + page;
    console.log(url);
    return GlycReSoft.ajaxWithContext(url).success(function(doc) {
      currentPage = page;
      displayTable.html(doc);
      return setupGlycopeptideTablePageHandler(page);
    });
  };
  return setup();
};

//# sourceMappingURL=view-glycopeptide-hypothesis.js.map
