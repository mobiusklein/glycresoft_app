from flask import Response, g, request, render_template, abort

from .form_cleaners import remove_empty_rows, intify
from .service_module import register_service

from werkzeug import secure_filename

from glycresoft_app.task.fasta_glycopeptide_hypothesis import BuildGlycopeptideHypothesisFasta
from glycresoft_app.task.mzid_glycopeptide_hypothesis import BuildGlycopeptideHypothesisMzId

app = make_glycopeptide_hypothesis = register_service("make_glycopeptide_hypothesis", __name__)


@app.route("/glycopeptide_search_space")
def build_glycopeptide_search_space():
    return render_template("glycopeptide_search_space.templ", manager=g.manager)


@app.route("/glycopeptide_search_space", methods=["POST"])
def build_glycopeptide_search_space_post():
    values = request.values
    print values
    constant_modifications = values.getlist("constant_modifications")
    variable_modifications = values.getlist("variable_modifications")
    enzyme = values.get("enzyme")
    hypothesis_name = values.get("hypothesis_name")

    protein_list = request.files["protein-list-file"]
    protein_list_type = values.get("proteomics-file-type")
    glycan_file = request.files.get("glycan-definition-file")
    glycan_database = values.get("glycan-database-source")
    glycan_file_type = values.get("glycans-file-format")

    glycan_options = {}

    max_missed_cleavages = intify(values.get("missed_cleavages"))
    maximum_glycosylation_sites = intify(values.get("max_glycosylation_combinations", 1))

    secure_protein_list = g.manager.get_temp_path(secure_filename(protein_list.filename))
    protein_list.save(secure_protein_list)

    if glycan_database == "" or glycan_database is None:
        glycan_file_type = "text"
        glycan_options["glycan_source_type"] = glycan_file_type

        secure_glycan_file = g.manager.get_temp_path(secure_filename(glycan_file.filename))
        glycan_file.save(secure_glycan_file)

        glycan_options["glycomics_source"] = secure_glycan_file
    else:
        option_type, option_id = glycan_database.split(",", 1)
        option_id = int(option_id)

        if option_type == "Hypothesis":
            option_type = "hypothesis"
            glycan_options["glycomics_source"] = option_id
        elif option_type == "Analysis":
            option_type = "analysis"
            glycan_options["glycomics_source"] = option_id

        glycan_options["glycan_source_type"] = option_type

    if protein_list_type == "fasta":
        task = BuildGlycopeptideHypothesisFasta(
            g.manager.connection_bridge, fasta_file=secure_protein_list, enzyme=enzyme,
            missed_cleavages=max_missed_cleavages, occupied_glycosites=maximum_glycosylation_sites,
            name=hypothesis_name, constant_modification=constant_modifications,
            variable_modification=variable_modifications, processes=4,
            glycan_source=glycan_options["glycomics_source"], glycan_source_type=glycan_options["glycan_source_type"])
        g.manager.add_task(task)
    elif protein_list_type == 'mzIdentML':
        protein_names = values.get("protein_names").split(",")
        task = BuildGlycopeptideHypothesisMzId(
            g.manager.connection_bridge, secure_protein_list, name=hypothesis_name,
            occupied_glycosites=maximum_glycosylation_sites, target_protein=protein_names,
            processes=4, glycan_source=glycan_options['glycomics_source'],
            glycan_source_type=glycan_options['glycan_source_type'])
        g.manager.add_task(task)
    else:
        abort(405)
    return Response("Task Scheduled")
