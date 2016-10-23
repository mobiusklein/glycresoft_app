class GlycanCompositionLCMSSearchPaginator extends PaginationBase
    pageUrl: "/view_glycan_lcms_analysis/{analysisId}/page/{page}"
    tableSelector: ".glycan-chromatogram-table"
    tableContainerSelector: "#chromatograms-table"
    rowSelector: '.glycan-match-row'

    constructor: (@analysisId, @handle, @controller) ->
        super(1) 

    getPageUrl: (page=1) ->
        @pageUrl.format {"page": page, "analysisId": @analysisId}

    rowClickHandler: (row) =>
        @controller.showGlycanCompositionDetailsModal row


class GlycanCompositionLCMSSearchTabView extends TabViewBase
    tabSelector: 'ul.tabs'
    tabList: ["chromatograms-plot", "chromatograms-table", "summary-abundance-plot"]
    defaultTab: "chromatograms-plot"
    updateUrl: '/view_glycan_lcms_analysis/{analysisId}/content'
    containerSelector: '#glycan-lcms-container'

    constructor: (@analysisId, @handle, @parent, updateHandlers) ->
        parent = @parent
        super(updateHandlers)

    getUpdateUrl: ->
        @updateUrl.format({'analysisId': @analysisId})


class GlycanCompositionLCMSSearchController
    containerSelector: '#glycan-lcms-container'
    glycanTableSelector: ".glycan-chromatogram-table"
    detailModalSelector: '#glycan-detail-modal'
    detailUrl: "/view_glycan_lcms_analysis/{analysisId}/details_for/{chromatogramId}"

    constructor: (@analysisId) ->
        @handle = $ @containerSelector
        @currentPage = 1
        @glycanTable = $ @glycanTableSelector
        @glycanDetailsModal = $ @detailModalSelector
        @paginator = new GlycanCompositionLCMSSearchPaginator(@analysisId, @handle, @)

        updateHandlers = [
            =>
                console.log("Running update handler 1")
                @paginator.setupTable()
            =>
                console.log("Running update handler 2")
                handle = $ @tabView.containerSelector
                $.get("/view_glycan_lcms_analysis/#{@analysisId}/chromatograms_chart").success (payload) ->
                    console.log("Chromatograms Retrieved")
                    handle.find("#chromatograms-plot").html(payload)
                $.get("/view_glycan_lcms_analysis/#{@analysisId}/abundance_bar_chart").success (payload) ->
                    console.log("Bar Chart Retrieved")
                    handle.find("#summary-abundance-plot").html(payload)
        ]

        @tabView = new GlycanCompositionLCMSSearchTabView(@analysisId, @handle, @, updateHandlers)

    updateView: ->
        console.log("updateView")
        @tabView.updateView()

    showGlycanCompositionDetailsModal: (row) ->
        handle = $ row
        id = handle.attr('data-target')
        modal = @getModal()
        url = @detailUrl.format {analysisId: @analysisId, chromatogramId: id}
        $.get(url).success (doc) ->
            modal.find('.modal-content').html doc
            $(".lean-overlay").remove()
            modal.openModal()

    getModal: ->
        $ @detailModalSelector

    unload: ->
        GlycReSoft.removeCurrentLayer()


viewGlycanCompositionPeakGroupingDatabaseSearchResults = ->
    glycanDetailsModal = undefined
    glycanTable = undefined
    currentPage = 1

    setup = ->
        updateView()
        $("#save-csv-file").click downloadCSV

    updateView = ->
        handle = $(this)

        $("#content-container").html("""<div class="progress"><div class="indeterminate"></div></div>""").fadeIn()
        GlycReSoft.ajaxWithContext('/view_database_search_results/results_view/').success((doc) ->
            $('#content-container').hide()
            $('#content-container').html(doc).fadeIn()
            tabs = $('ul.tabs')
            tabs.tabs()
            if GlycReSoft.context['view-active-tab'] != undefined
                console.log GlycReSoft.context['view-active-tab']
                $('ul.tabs').tabs 'select_tab', GlycReSoft.context['view-active-tab']
            else
                $('ul.tabs').tabs 'select_tab', 'glycome-overview'
            $('.indicator').addClass 'indigo'
            $('ul.tabs .tab a').click ->
                GlycReSoft.context['view-active-tab'] = $(this).attr('href').slice(1)
            glycanDetailsModal = $ '#glycan-detail-modal'
            glycanTable = $ "#glycan-table"
            # doZoom("#glycome-overview svg g")
            updateGlycanCompositionTablePage 1
        ).error (error) ->
            console.log arguments

    showGlycanCompositionDetailsModal = ->
        handle = $(this)
        id = handle.attr('data-target')
        console.log id
        PartialSource.glycanCompositionDetailsModal {"id": id}, (doc) ->
            glycanDetailsModal.find('.modal-content').html doc
            $(".lean-overlay").remove()
            glycanDetailsModal.openModal()

    unload = ->
        GlycReSoft.removeCurrentLayer()


    downloadCSV = ->
        handle = $(this)
        id = handle.attr('data-target')
        $.ajax "/view_database_search_results/export_csv/" + id,
                data: JSON.stringify({"context": GlycReSoft.context, "settings": GlycReSoft.settings}),
                contentType: "application/json"
                type: 'POST'

    setup()
