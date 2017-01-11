var ActionBook, Analysis, ErrorLogURL, Hypothesis, Sample, Task, makeAPIGet, makeParameterizedAPIGet;

ActionBook = {
  home: {
    container: '#home-layer',
    name: 'home-layer',
    closeable: false
  },
  addSample: {
    contentURL: '/add_sample',
    name: 'add-sample'
  },
  glycanCompositionSearch: {
    contentURL: '/search_glycan_composition/run_search',
    name: 'search-glycan-composition'
  },
  glycopeptideSequenceSearch: {
    contentURL: '/search_glycopeptide_sequences/run_search',
    name: "search-glycopeptide-sequences"
  },
  naiveGlycopeptideSearchSpace: {
    contentURL: "/glycopeptide_search_space",
    name: "glycopeptide-search-space"
  },
  naiveGlycanSearchSpace: {
    contentURL: "/glycan_search_space",
    name: "glycan-search-space"
  },
  viewAnalysis: {
    contentURLTemplate: "/view_analysis/{analysis_id}",
    name: "view-analysis",
    method: "post"
  },
  viewHypothesis: {
    contentURLTemplate: "/view_hypothesis/{uuid}",
    method: "post"
  }
};

makeAPIGet = function(url) {
  return function(callback) {
    return $.get(url).success(callback);
  };
};

makeParameterizedAPIGet = function(url) {
  return function(params, callback) {
    return $.get(url.format(params)).success(callback);
  };
};

Hypothesis = {
  all: makeAPIGet("/api/hypotheses"),
  get: makeParameterizedAPIGet("/api/hypotheses/{}")
};

Sample = {
  all: makeAPIGet("/api/samples")
};

Analysis = {
  all: makeAPIGet("/api/analyses")
};

Task = {
  all: makeAPIGet("/api/tasks")
};

ErrorLogURL = "/log_js_error";

//# sourceMappingURL=bind-urls.js.map
