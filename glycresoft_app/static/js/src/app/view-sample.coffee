

class SampleViewController
    chromatogramTableSelector: "#chromatogram-table"
    saveResultBtnSelector: "#save-result-btn"

    constructor: (@sampleUUID) ->
        @initializeChromatogramTable()

    saveCSV: ->
        $.get("/view_sample/#{@sampleUUID}/to-csv").then (payload) =>
            if GlycReSoft.isNativeClient()
                nativeClientMultiFileDownloadDirectory (directory) =>
                    $.post("/internal/move_files", {
                        filenames: [payload.filename],
                        destination: directory
                    }).success ()->
                        openDirectoryExternal(directory)
            else
                GlycReSoft.downloadFile payload.filename

    initializeChromatogramTable: ->
        console.log "Loading Chromatogram Table"
        $.get("/view_sample/#{@sampleUUID}/chromatogram_table").then (content) =>
            console.log "Writing Chromatogram Table"
            $(@chromatogramTableSelector).html content
            $(@saveResultBtnSelector).click => @saveCSV()
            materialRefresh()
