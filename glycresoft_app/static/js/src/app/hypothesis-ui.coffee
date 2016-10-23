Application::renderHypothesisListAt = (container)->
    chunks = []
    template = ''
    self = @
    for hypothesis in _.sortBy(_.values(@hypotheses), (o) -> o.id)
        if hypothesis.is_decoy
            continue
        row = $("
    <div data-id=#{hypothesis.id} data-uuid=#{hypothesis.uuid} class='list-item clearfix'>
        <span class='handle'>#{hypothesis.id}. #{hypothesis.name.replace('_', ' ')}</span>
        <small class='right' style='display:inherit'>
            #{if hypothesis.hypothesis_type? then hypothesis.hypothesis_type else '-' }
            <a class='remove-hypothesis mdi mdi-close'></a>
        </small>
    </div>
    ")
        chunks.push row

        row.click (event) ->
            handle = $ @
            hypothesisId = handle.attr("data-id")
            uuid = handle.attr("data-uuid")
            self.addLayer ActionBook.viewHypothesis, {"uuid": uuid}
            layer = self.lastAdded
            self.setShowingLayer layer
        row.find(".remove-hypothesis").click (event) -> 
            handle = $ @

    $(container).html chunks

Application.initializers.push ->
    @on "render-hypotheses", =>
        @renderHypothesisListAt ".hypothesis-list"
