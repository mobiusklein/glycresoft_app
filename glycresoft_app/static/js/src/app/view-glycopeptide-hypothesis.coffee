class GlycopeptideHypothesisPaginator extends PaginationBase
    tableSelector: "#display-table-container"
    tableContainerSelector: "#display-table-container"
    rowSelector: "#display-table-container tbody tr"
    pageUrl: "/view_glycopeptide_hypothesis/{hypothesisId}/{proteinId}/page/{page}"

    constructor: (@hypothesisId, @handle, @controller) ->
        super(1) 

    getPageUrl: (page=1) ->
        @pageUrl.format {"page": page, "hypothesisId": @hypothesisId, "proteinId": @controller.proteinId}

    rowClickHandler: (row) =>
        console.log row


class GlycopeptideHypothesisController
    containerSelector: '#hypothesis-protein-glycopeptide-container'
    proteinTableRowSelector: '.protein-list-table tbody tr'
    proteinContainerSelector: '#protein-container'
    proteinViewUrl: "/view_glycopeptide_hypothesis/{hypothesisId}/{proteinId}/view"

    constructor: (@hypothesisId, @proteinId) ->
        @handle = $ @containerSelector
        @paginator = new GlycopeptideHypothesisPaginator(@hypothesisId, @handle, @)
        @setup()

    setup: ->
        self = @
        $(@proteinTableRowSelector).click (event) ->
            self.proteinChoiceHandler @
        self.proteinChoiceHandler $(@proteinTableRowSelector)[0]

    getProteinViewUrl: (proteinId) ->
        @proteinViewUrl.format({'hypothesisId': @hypothesisId, 'proteinId', proteinId})

    proteinChoiceHandler: (proteinRow) =>
        handle = $ proteinRow
        @proteinId = id = handle.attr('data-target')
        proteinContainer = $ @proteinContainerSelector
        proteinContainer.html("""<div class="progress"><div class="indeterminate"></div></div>""").fadeIn()

        url = @getProteinViewUrl id
        GlycReSoft.ajaxWithContext(url).success (doc) =>
            proteinContainer.hide()
            proteinContainer.html(doc).fadeIn()
            GlycReSoft.context["current_protein"] = id
            @paginator.setupTable()




viewGlycopeptideHypothesis = (hypothesisId) ->
    displayTable = undefined
    currentPage = 1
    proteinContainer = undefined
    proteinId = undefined

    setup = ->
        proteinContainer = $("#protein-container")
        $('.protein-list-table tbody tr').click updateProteinChoice
        updateProteinChoice.apply $('.protein-list-table tbody tr')

    setupGlycopeptideTablePageHandler = (page=1) ->        
        $('.display-table tbody tr').click(->)
        $(':not(.disabled) .next-page').click(-> updateCompositionTablePage(page + 1))
        $(':not(.disabled) .previous-page').click(-> updateCompositionTablePage(page - 1))
        $('.pagination li :not(.active)').click ->
            nextPage = $(@).attr("data-index")
            if nextPage?
                nextPage = parseInt nextPage
                updateCompositionTablePage nextPage

    updateProteinChoice = ->
        handle = $(this)
        proteinId = id = handle.attr('data-target')
        proteinContainer.html("""<div class="progress"><div class="indeterminate"></div></div>""").fadeIn()

        url = "/view_glycopeptide_hypothesis/protein_view/#{proteinId}"
        $.post(url, {"settings": GlycReSoft.settings, "context": GlycReSoft.context}).success (doc) ->
            proteinContainer.hide()
            proteinContainer.html(doc).fadeIn()
            GlycReSoft.context["current_protein"] = id
            displayTable = $("#display-table-container")
            updateCompositionTablePage(1)
        .error (error) ->
            console.log arguments


    updateCompositionTablePage = (page=1) ->
        url = "/view_glycopeptide_hypothesis/protein_view/#{proteinId}/#{page}"
        console.log(url)
        GlycReSoft.ajaxWithContext(url).success (doc) ->
            currentPage = page
            displayTable.html doc
            setupGlycopeptideTablePageHandler page

    setup()
