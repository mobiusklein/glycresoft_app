"use strict"
# Depends on jQuery


class ChromatogramSpecification
    constructor: (description) ->
        @entity = description.entity
        @score = description.score
        @id = description.id
        @startTime = description.startTime
        @endTime = description.endTime
        @apexTime = description.apexTime
        @selected = false

    render: (container) ->
        entry = """
        <div class="chromatogram-entry row" data-id='#{@id}' data-entity='#{@entity}'>
            <div class='col s4 chromatogram-entry-entity'>#{@entity}</div>
            <div class='col s2'>#{@score.toFixed(3)}</div>
            <div class='col s2'>#{@startTime.toFixed(3)}</div>
            <div class='col s2'>#{@apexTime.toFixed(3)}</div>
            <div class='col s2'>#{@endTime.toFixed(3)}</div>
        </div>
        """
        container.append($(entry))


class ChromatogramSelectionList
    constructor: (@container, @chromatogramSpecifications) ->
        @selectedChromatograms = {}

    getSpecificationByID: (id) ->
        for spec in @chromatogramSpecifications
            if spec.id == id
                return spec
        return undefined

    initialize: ->
        self = @
        @container.on 'click', '.chromatogram-entry', ->
            console.log(@, self)
            spec = self.getSpecificationByID(parseInt(@dataset.id))
            isSelected = self.selectedChromatograms[spec.id]
            if not isSelected?
                isSelected = false
            if not isSelected
                self.selectedChromatograms[spec.id] = true
                @classList.add("selected")
            else
                self.selectedChromatograms[spec.id] = false
                @classList.remove("selected")

    find: (selector) ->
        return @container.find(selector)

    render: ->
        @container.empty()
        chromatograms = @chromatogramSpecifications
        chromatograms.sort (a, b) ->
            a = a.entity
            b = b.entity
            if a > b
                return 1
            else if a < b
                return -1
            return 0
        for entry in chromatograms
            entry.render @container
        @initialize()

    pack: ->
        selectedIds = []
        for id, selected of @selectedChromatograms
            if selected
                selectedIds.push(id)
        return selectedIds


class ChromatogramComposer
    constructor: (@container, @chromatogramSpecifications, @renderingEndpoint) ->
        @chromatogramSelectionListContainer = @container.find(".chromatogram-selection-list")
        @chromatogramPlotContainer = @container.find(".chromatogram-plot")
        if not @chromatogramSpecifications?
            @chromatogramSpecifications = []
        @chromatogramSelectionList = new ChromatogramSelectionList(
            @chromatogramSelectionListContainer,
            @chromatogramSpecifications)
        @drawButton = @container.find(".draw-plot-btn")
        @drawButton.click =>
            @updatePlot()

    setChromatograms: (chromatograms) ->
        @chromatogramSpecifications = chromatograms.map((obj) -> new ChromatogramSpecification(obj))
        @chromatogramSelectionList.chromatogramSpecifications = @chromatogramSpecifications

    updatePlot: (callback) ->
        $.post(@renderingEndpoint, {'selected_ids': @chromatogramSelectionList.pack()}).then (result) =>
            console.log result.status
            @chromatogramPlotContainer.html(result.payload)
            if callback?
                callback(@)

    initialize: (callback) ->
        @hide()
        @chromatogramSelectionList.render()
        @show()

    hide: ->
        @container.hide()

    show: ->
        @container.show()


makeChromatogramComposer = (uid, callback, chromatogramSpecifications, renderingEndpoint) ->
    template = """
    <div class='chromatogram-composer' id='chromatogram-composer-#{uid}'>
        <div class='chromatogram-composer-container-inner'>
            <div class='row'>
                <h5 class='section-title'>Chromatogram Plot Composer</h5>
            </div>
            <div class='row'>
                <div class='col s6'>
                    <div class='chromatogram-selection-header row'>
                        <div class='col s4'>Entity</div>
                        <div class='col s2'>Score</div>
                        <div class='col s2'>Start Time</div>
                        <div class='col s2'>Apex Time</div>
                        <div class='col s2'>End Time</div>
                    </div>
                    <div class='chromatogram-selection-list'>
                    </div>
                </div>
                <div class='col s6'>
                    <div class='chromatogram-plot'>
                    </div>
                </div>
            </div>
            <div class='row'>
                <a class='btn draw-plot-btn'>Draw</a>
            </div>
        </div>
    </div>
    """
    handle = $(template)
    inst = new ChromatogramComposer(handle, [], renderingEndpoint)
    inst.setChromatograms(chromatogramSpecifications)
    inst.initialize(callback)
    return inst
