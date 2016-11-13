samplePreprocessingPresets = [
    {
        name: "Negative Mode Glycomics"
        max_charge: -9
        ms1_score_threshold: 15
        ms1_averagine: "glycan"
        max_missing_peaks: 1
    }
    {
        name: "Positive Mode Glycoproteomics"
        max_charge: 12
        max_missing_peaks: 1
        ms1_score_threshold: 35
        ms1_averagine: "glycopeptide"
        msn_score_threshold: 5
        msn_averagine: 'peptide'
    }
]

setSamplePreprocessingConfiguration = (name) ->
    found = false
    for config in samplePreprocessingPresets
        if config.name == name
            found = true
            break
    if not found
        return
    form = $("#add-sample")
    form.find("#maximum-charge-state").val(config.max_charge)
    form.find("#missed-peaks").val(config.max_missing_peaks)
    form.find('#ms1-minimum-isotopic-score').val(config.ms1_score_threshold)
    form.find('#ms1-averagine').val(config.ms1_averagine)
    if config.msn_score_threshold?
        form.find('#msn-minimum-isotopic-score').val(config.msn_score_threshold)
    if config.msn_averagine?
        form.find('#msn-averagine').val(config.msn_averagine)

makePresetSelector = (container) ->
    elem = $('''<select style='browser-default' name='preset-configuration>
    </select>''')
    for preset in samplePreprocessingPresets
        elem.append($("<option value='#{preset.name}'>#{preset.name}</option>"))
    container.append(elem)
    elem.change (event, name) ->
        console.log(arguments)
        # setSamplePreprocessingConfiguration
