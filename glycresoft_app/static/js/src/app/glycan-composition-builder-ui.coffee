# Depends on jQuery



class MonosaccharideInputWidgetGrid
    template: """
    <div class='monosaccharide-row row'>
        <div class='input-field col s2'>
            <label for='mass_shift_name'>Residue Name</label>
            <input class='monosaccharide-name center-align' type='text' name='monosaccharide_name' placeholder='Name'>
        </div>
        <div class='input-field col s2'>
            <label for='monosaccharide_mass_delta'>Lower Bound</label>
            <input class='lower-bound numeric-entry' min='0' type='number' name='monosaccharide_lower_bound' placeholder='Bound'>
        </div>
        <div class='input-field col s2'>
            <label for='monosaccharide_max_count'>Upper Bound</label>    
            <input class='upper-bound numeric-entry' type='number' min='0' placeholder='Bound' name='monosaccharide_upper_bound'>
        </div>
    </div>
    """

    constructor: (container)->
        @counter = 0
        @container = $(container)
        @monosaccharides = {}

    update: ->
        monosaccharides = {}
        for row in @container.find(".monosaccharide-row")
            row = $(row)
            entry = {
                name: row.find(".monosaccharide-name").val()
                lower_bound: row.find(".lower-bound").val()
                upper_bound: row.find(".upper-bound").val()
                # composition: row.find(".monosaccharide-composition").val()
            }
            if entry.name == ""
                continue
            if entry.name of monosaccharides
                row.addClass "warning"
                pos = row.position()
                notify = new TinyNotification(pos.top + 50, pos.left, "This monosaccharide is already present.", row)
                row.data("tinyNotification", notify)
            else
                row.removeClass "warning"
                if row.data("tinyNotification")?
                    notif = row.data("tinyNotification")
                    notif.dismiss()
                    row.data("tinyNotification", undefined)
                monosaccharides[entry.name] = entry
        @monosaccharides = monosaccharides

    addEmptyRowOnEdit: (addHeader=false) ->
        row = $(@template)
        if !addHeader
            row.find("label").remove()
        @container.append(row)
        row.data("counter", ++@counter)
        self = @
        callback = (event) ->
            if row.data("counter") == self.counter
                self.addEmptyRowOnEdit(false)
            $(@).parent().find("label").removeClass("active")
        row.find("input").change callback
        row.find("input").change => @update()

    addRow: (name, lower, upper, composition, addHeader=false) ->
        row = $(@template)
        if !addHeader
            row.find("label").remove()
        @counter += 1
        row.find(".monosaccharide-name").val(name)
        row.find(".lower-bound").val(lower)
        row.find(".upper-bound").val(upper)
        # row.find(".monosaccharide-composition").val(composition)
        @container.append(row)
        row.find("input").change => @update()
        @update()


class ConstraintInputGrid
    template: """
    <div class="monosaccharide-constraints-row row">
        <div class='input-field col s2'>
            <label for='left_hand_side'>Limit</label>
            <input class='monosaccharide-name center-align' type='text' name='left_hand_side' placeholder='Name'>
        </div>
        <div class='input-field col s2' style='padding-left: 2px;padding-right: 2px;'>
            <select class='browser-default center-align' name='operator'>
                <option>=</option>
                <option>!=</option>
                <option>&gt;</option>
                <option>&lt;</option>
                <option>&gt;=</option>
                <option>&lt;=</option>
            </select>
        </div>
        <div class='input-field col s4 constrained-value-cell'>
            <label for='right_hand_side'>Constrained Value</label>
            <input class='monosaccharide-name constrained-value' type='text' name='right_hand_side' placeholder='Name/Value'>
        </div>
    </div>
    """

    constructor: (container, monosaccharideGrid)->
        @counter = 0
        @container = $(container)
        @constraints = []
        @monosaccharideGrid = monosaccharideGrid

    addEmptyRowOnEdit: (addHeader=false) ->
        row = $(@template)
        if !addHeader
            row.find("label").remove()
        @container.append(row)
        row.data("counter", ++@counter)
        self = @
        callback = (event) ->
            if row.data("counter") == self.counter
                self.addEmptyRowOnEdit(false)
            $(@).parent().find("label").removeClass("active")
        row.find("input").change callback
        row.find("input").change => @update()

    addRow: (lhs, op, rhs, addHeader=false) ->
        row = $(@template)
        if !addHeader
            row.find("label").remove()
        @counter += 1
        row.find("input[name='left_hand_side']").val(lhs)
        row.find("select[name='operator']").val(op)
        row.find("input[name='right_hand_side']").val(rhs)
        @container.append(row)
        row.find("input").change => @update()
        console.log(row)
        @update()

    update: ->
        constraints = []
        for row in @container.find(".monosaccharide-constraints-row")
            row = $(row)
            console.log(row)
            entry = {
                lhs: row.find("input[name='left_hand_side']").val()
                operator: row.find("select[name='operator']").val()
                rhs: row.find("input[name='right_hand_side']").val()
            }
            if entry.lhs == "" or entry.rhs == ""
                continue
            # getMonosaccharide = (name) ->
            #     console.log("getMonosaccharide", name)
            #     /^(\d+)(.+)/.exec(name)[2]
            # if not (getMonosaccharide(entry.lhs) of @monosaccharideGrid.monosaccharides)
            #     row.addClass "warning"
            #     notify = new TinyNotification(0, 0, "#{entry.lhs} is not defined.", row)
            #     row.data("tinyNotification", notify)
            #     console.log(notify)

            # else if not (getMonosaccharide(entry.rhs) of @monosaccharideGrid.monosaccharides)
            #     row.addClass("warning")
            #     # In case we fall through from a previous error state in the lhs
            #     if row.data("tinyNotification")?
            #         notif = row.data("tinyNotification")
            #         notif.dismiss()
            #         row.data("tinyNotification", undefined)
            #     notify = new TinyNotification(0, 0, "#{entry.rhs} is not defined.", row)
            #     row.data("tinyNotification", notify)
            #     console.log(notify)
            # else
            #     row.removeClass("warning")
            #     if row.data("tinyNotification")?
            #         notif = row.data("tinyNotification")
            #         notif.dismiss()
            #         row.data("tinyNotification", undefined)
            constraints.push(entry)
        console.log(constraints)
        @constraints = constraints
