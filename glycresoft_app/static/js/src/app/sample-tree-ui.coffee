composeSampleAnalysisTree = (bundle) ->
    samples = bundle.samples
    analyses = bundle.analyses
    sampleMap = {}
    for name of samples
        sampleMap[name] = []

    for id, analysis of analyses
        sampleName = analysis.sample_name
        if !sampleMap[sampleName]?
            sampleMap[sampleName] = []

        sampleMap[sampleName].push(analysis)

    trees = []
    for name, analysisList of sampleMap
        entry = {
            "sample": samples[name],
            "analyses": _.sortBy(analysisList, "name")
        }
        trees.push(entry)
    _.sortBy(trees, (obj) -> obj.sample.name)
    return trees

Application::renderSampleTree = (container) ->
    container = $(container)
    container.empty()
    trees = composeSampleAnalysisTree(@)
    rendered = []
    cleanNamePattern = /_/g
    for tree in trees
        sample = tree.sample
        analyses = tree.analyses

        analysisChunks = []
        
        if analyses.length > 0
            expander = """
            <span class="expanded-display-control indigo-text">
                <i class="material-icons">check_box_outline_blank</i>
            </span>
            """
        else
            expander = ""
        prefix = """
        <div class='project-entry'>
            <div class="project-item" data-uuid='#{sample.uuid}'>
                <span class='project-sample-name'>
                    #{expander}
                    #{sample.name.replace(cleanNamePattern, " ")}
                </span>
                <div class="analysis-entry-list">
        """
        for analysis in analyses
            analysisChunk = """
                <div class='analysis-entry-item' data-uuid='#{analysis.uuid}'>
                    <span class='project-analysis-name'>
                        #{analysis.name.replace(" at " + sample.name, "").replace(cleanNamePattern, " ")}
                    </span>
                </div>
            """
            analysisChunks.push analysisChunk
        suffix = """
                </div>
            </div>
        </div>
        """
        entry = [
            prefix,
            analysisChunks.join("\n"),
            suffix
        ].join("\n")
        rendered.push(entry)
    container.append(rendered)

Application.initializers.push ->
    @on "render-samples", =>
        @renderSampleTree ".projects-entry-list"
    @on "render-analyses", =>
        @renderSampleTree ".projects-entry-list"

