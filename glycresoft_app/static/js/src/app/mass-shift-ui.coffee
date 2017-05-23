

MassShiftInputWidget = (()->
    template = """
    <div class='mass-shift-row row'>
        <div class='input-field col s3' style='margin-right:55px; margin-left:30px;'>
            <label for='mass_shift_name'>Name or Formula</label>
            <input class='mass-shift-name' type='text' name='mass_shift_name' placeholder='Name/Formula'>
        </div>
        <div class='input-field col s2'>
            <label for='mass_shift_max_count'>Maximum Count</label>    
            <input class='max-count' type='number' min='0' placeholder='Maximum Count' name='mass_shift_max_count'>
        </div>
    </div>
    """

    counter = 0

    addEmptyRowOnEdit = (container, addHeader=true) ->
        container = $(container)
        if addHeader
            row = $(template)
        else
            row = $(template)
            row.find("label").remove()
        container.append(row)
        row.data("counter", ++counter)
        callback = (event) ->
            if row.data("counter") == counter
                addEmptyRowOnEdit(container, false)
            $(@).parent().find("label").removeClass("active")
        row.find("input").change callback

    return addEmptyRowOnEdit
)()
