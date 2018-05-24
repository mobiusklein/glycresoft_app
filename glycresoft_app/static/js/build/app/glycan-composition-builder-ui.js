"use strict";
var ConstraintInputGrid, MonosaccharideInputWidgetGrid;

MonosaccharideInputWidgetGrid = (function() {
  MonosaccharideInputWidgetGrid.prototype.template = "<div class='monosaccharide-row row'>\n    <div class='input-field col s2'>\n        <label for='mass_shift_name'>Residue Name</label>\n        <input class='monosaccharide-name center-align' type='text' name='monosaccharide_name' placeholder='Name'>\n    </div>\n    <div class='input-field col s2'>\n        <label for='monosaccharide_mass_delta'>Lower Bound</label>\n        <input class='lower-bound numeric-entry' min='0' type='number' name='monosaccharide_lower_bound' placeholder='Bound'>\n    </div>\n    <div class='input-field col s2'>\n        <label for='monosaccharide_max_count'>Upper Bound</label>    \n        <input class='upper-bound numeric-entry' type='number' min='0' placeholder='Bound' name='monosaccharide_upper_bound'>\n    </div>\n</div>";

  function MonosaccharideInputWidgetGrid(container) {
    this.counter = 0;
    this.container = $(container);
    this.monosaccharides = {};
    this.validatedMonosaccharides = new Set();
  }

  MonosaccharideInputWidgetGrid.prototype.update = function() {
    var continuation, entry, i, len, monosaccharides, notif, notify, pos, ref, row, validatedMonosaccharides;
    validatedMonosaccharides = new Set();
    monosaccharides = {};
    ref = this.container.find(".monosaccharide-row");
    for (i = 0, len = ref.length; i < len; i++) {
      row = ref[i];
      row = $(row);
      entry = {
        name: row.find(".monosaccharide-name").val(),
        lower_bound: row.find(".lower-bound").val(),
        upper_bound: row.find(".upper-bound").val()
      };
      if (entry.name === "") {
        row.removeClass("warning");
        if (row.data("tinyNotification") != null) {
          notif = row.data("tinyNotification");
          notif.dismiss();
          row.data("tinyNotification", void 0);
        }
        continue;
      }
      if (entry.name in monosaccharides) {
        row.addClass("warning");
        pos = row.position();
        if (row.data("tinyNotification") != null) {
          notif = row.data("tinyNotification");
          notif.dismiss();
        }
        notify = new TinyNotification(pos.top + 50, pos.left, "This residue is already present.", row);
        row.data("tinyNotification", notify);
      } else {
        row.removeClass("warning");
        if (row.data("tinyNotification") != null) {
          notif = row.data("tinyNotification");
          notif.dismiss();
          row.data("tinyNotification", void 0);
        }
        monosaccharides[entry.name] = entry;
        continuation = (function(_this) {
          return function(gridRow, entry, validatedMonosaccharides) {
            return $.post("/api/validate-iupac", {
              "target_string": entry.name
            }).then(function(validation) {
              console.log("Validation of", entry.name, validation);
              if (validation.valid) {
                validatedMonosaccharides.add(validation.message);
                if (!(entry.name in monosaccharides)) {
                  gridRow.removeClass("warning");
                  if (gridRow.data("tinyNotification") != null) {
                    notif = gridRow.data("tinyNotification");
                    notif.dismiss();
                    return gridRow.data("tinyNotification", void 0);
                  }
                }
              } else {
                gridRow.addClass("warning");
                pos = gridRow.position();
                if (gridRow.data("tinyNotification") != null) {
                  notif = gridRow.data("tinyNotification");
                  notif.dismiss();
                }
                notify = new TinyNotification(pos.top + 50, pos.left, validation.message, gridRow);
                return gridRow.data("tinyNotification", notify);
              }
            });
          };
        })(this);
        continuation(row, entry, validatedMonosaccharides);
      }
    }
    this.validatedMonosaccharides = validatedMonosaccharides;
    return this.monosaccharides = monosaccharides;
  };

  MonosaccharideInputWidgetGrid.prototype.addEmptyRowOnEdit = function(addHeader) {
    var callback, row, self;
    if (addHeader == null) {
      addHeader = false;
    }
    row = $(this.template);
    if (!addHeader) {
      row.find("label").remove();
    }
    this.container.append(row);
    row.data("counter", ++this.counter);
    self = this;
    callback = function(event) {
      if (row.data("counter") === self.counter) {
        self.addEmptyRowOnEdit(false);
      }
      return $(this).parent().find("label").removeClass("active");
    };
    row.find("input").change(callback);
    return row.find("input").change((function(_this) {
      return function() {
        return _this.update();
      };
    })(this));
  };

  MonosaccharideInputWidgetGrid.prototype.addRow = function(name, lower, upper, composition, addHeader) {
    var row;
    if (addHeader == null) {
      addHeader = false;
    }
    row = $(this.template);
    if (!addHeader) {
      row.find("label").remove();
    }
    this.counter += 1;
    row.find(".monosaccharide-name").val(name);
    row.find(".lower-bound").val(lower);
    row.find(".upper-bound").val(upper);
    this.container.append(row);
    row.find("input").change((function(_this) {
      return function() {
        return _this.update();
      };
    })(this));
    return this.update();
  };

  return MonosaccharideInputWidgetGrid;

})();

ConstraintInputGrid = (function() {
  ConstraintInputGrid.prototype.template = "<div class=\"monosaccharide-constraints-row row\">\n    <div class='input-field col s2'>\n        <label for='left_hand_side'>Limit</label>\n        <input class='monosaccharide-name center-align' type='text' name='left_hand_side' placeholder='Name'>\n    </div>\n    <div class='input-field col s2' style='padding-left: 2px;padding-right: 2px;'>\n        <select class='browser-default center-align' name='operator'>\n            <option>=</option>\n            <option>!=</option>\n            <option>&gt;</option>\n            <option>&lt;</option>\n            <option>&gt;=</option>\n            <option>&lt;=</option>\n        </select>\n    </div>\n    <div class='input-field col s4 constrained-value-cell'>\n        <label for='right_hand_side'>Constrained Value</label>\n        <input class='monosaccharide-name constrained-value' type='text' name='right_hand_side' placeholder='Name/Value'>\n    </div>\n</div>";

  function ConstraintInputGrid(container, monosaccharideGrid) {
    this.counter = 0;
    this.container = $(container);
    this.constraints = [];
    this.monosaccharideGrid = monosaccharideGrid;
  }

  ConstraintInputGrid.prototype.addEmptyRowOnEdit = function(addHeader) {
    var callback, row, self;
    if (addHeader == null) {
      addHeader = false;
    }
    row = $(this.template);
    if (!addHeader) {
      row.find("label").remove();
    }
    this.container.append(row);
    row.data("counter", ++this.counter);
    self = this;
    callback = function(event) {
      if (row.data("counter") === self.counter) {
        self.addEmptyRowOnEdit(false);
      }
      return $(this).parent().find("label").removeClass("active");
    };
    row.find("input").change(callback);
    return row.find("input").change((function(_this) {
      return function() {
        return _this.update();
      };
    })(this));
  };

  ConstraintInputGrid.prototype.addRow = function(lhs, op, rhs, addHeader) {
    var row;
    if (addHeader == null) {
      addHeader = false;
    }
    row = $(this.template);
    if (!addHeader) {
      row.find("label").remove();
    }
    this.counter += 1;
    row.find("input[name='left_hand_side']").val(lhs);
    row.find("select[name='operator']").val(op);
    row.find("input[name='right_hand_side']").val(rhs);
    this.container.append(row);
    row.find("input").change((function(_this) {
      return function() {
        return _this.update();
      };
    })(this));
    console.log(row);
    return this.update();
  };

  ConstraintInputGrid.prototype.update = function() {
    var constraints, entry, i, len, ref, row;
    constraints = [];
    ref = this.container.find(".monosaccharide-constraints-row");
    for (i = 0, len = ref.length; i < len; i++) {
      row = ref[i];
      row = $(row);
      console.log(row);
      this.clearError(row);
      entry = {
        lhs: row.find("input[name='left_hand_side']").val(),
        operator: row.find("select[name='operator']").val(),
        rhs: row.find("input[name='right_hand_side']").val(),
        "row": row
      };
      if (entry.lhs === "" || entry.rhs === "") {
        continue;
      }
      this.updateSymbols(entry);
      constraints.push(entry);
    }
    console.log(constraints);
    return this.constraints = constraints;
  };

  ConstraintInputGrid.prototype.clearError = function(row) {
    row.find("input[name='left_hand_side']")[0].setCustomValidity("");
    return row.find("input[name='right_hand_side']")[0].setCustomValidity("");
  };

  ConstraintInputGrid.prototype.updateSymbols = function(entry) {
    return $.post("/api/parse-expression", {
      "expressions": [entry.lhs, entry.rhs]
    }).then((function(_this) {
      return function(response) {
        var knownSymbols, lhsSymbols, ref, rhsSymbols, undefinedSymbolsLeft, undefinedSymbolsRight;
        console.log("Expression Symbols", response.symbols);
        ref = response.symbols, lhsSymbols = ref[0], rhsSymbols = ref[1];
        entry.lhsSymbols = lhsSymbols;
        entry.rhsSymbols = rhsSymbols;
        console.log(entry, lhsSymbols, rhsSymbols);
        knownSymbols = new Set(_this.monosaccharideGrid.validatedMonosaccharides);
        undefinedSymbolsLeft = new Set(Array.from(entry.lhsSymbols).filter(function(x) {
          return !knownSymbols.has(x);
        }));
        if (undefinedSymbolsLeft.size > 0) {
          entry.row.find("input[name='left_hand_side']")[0].setCustomValidity("Symbols (" + (Array.from(undefinedSymbolsLeft)) + ") are not in the hypothesis");
        } else {
          entry.row.find("input[name='left_hand_side']")[0].setCustomValidity("");
        }
        undefinedSymbolsRight = new Set(Array.from(entry.rhsSymbols).filter(function(x) {
          return !knownSymbols.has(x);
        }));
        if (undefinedSymbolsRight.size > 0) {
          return entry.row.find("input[name='right_hand_side']")[0].setCustomValidity("Symbols (" + (Array.from(undefinedSymbolsRight)) + ") are not in the hypothesis");
        } else {
          return entry.row.find("input[name='right_hand_side']")[0].setCustomValidity("");
        }
      };
    })(this));
  };

  return ConstraintInputGrid;

})();

//# sourceMappingURL=glycan-composition-builder-ui.js.map
