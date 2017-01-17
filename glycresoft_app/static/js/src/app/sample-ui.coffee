Application::renderSampleListAt = (container)->
    chunks = []
    self = @
    for sample in _.sortBy(_.values(@samples), (o) -> o.id)
        row = $("
    <div data-name=#{sample.name} class='list-item sample-entry clearfix' data-uuid='#{sample.uuid}' data-id='#{sample.id}'>
        <span class='handle user-provided-name'>#{sample.name.replace(/_/g, ' ')}</span>
        <small class='right' style='display:inherit'>
            #{sample.sample_type} <span class='status-indicator'></span>
            <a class='remove-sample mdi mdi-close'></a>
        </small>
    </div>
    ")
        sampleStatusDisplay = row.find(".status-indicator")
        if not sample.completed
            sampleStatusDisplay.html("<small class='yellow-text'>(Incomplete)</small>")
        chunks.push row
        row.click (event) ->
            handle = $ @
            sampleId = handle.attr("data-id")
            uuid = handle.attr("data-uuid")
            self.addLayer ActionBook.viewSample, {"sample_id": sampleId}
            layer = self.lastAdded
            self.setShowingLayer layer
        row.find(".remove-sample").click (event) -> 
            handle = $ @
            console.log handle

    $(container).html chunks

Application.initializers.push ->
    @on "render-samples", =>
        @renderSampleListAt ".sample-list"
