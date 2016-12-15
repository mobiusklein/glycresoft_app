import matplotlib
import os
import operator
import time
import urllib

from glycopeptidepy import PeptideSequence
from glypy.composition.glycan_composition import FrozenGlycanComposition

from jinja2 import Environment, PackageLoader, Undefined, FileSystemLoader, escape
from jinja2 import nodes
from jinja2.ext import Extension

try:
    from cStringIO import StringIO
except:
    from io import StringIO

from matplotlib import rcParams as mpl_params
from matplotlib import pyplot as plt
from matplotlib.axes import Axes

from glycan_profiling.plotting import colors


mpl_params.update({
    'figure.facecolor': 'white',
    'figure.edgecolor': 'white',
    'font.size': 10,
    # 72 dpi matches SVG
    # this only affects PNG export, as SVG has no dpi setting
    'savefig.dpi': 72,
    # 10pt still needs a little more room on the xlabel:
    'figure.subplot.bottom': .125})


def png_plot(figure, **kwargs):
    data_buffer = render_plot(figure, format='png', **kwargs)
    return b"<img src='data:image/png;base64,%s'>" % urllib.quote(data_buffer.getvalue().encode("base64"))


def svg_plot(figure, **kwargs):
    data_buffer = render_plot(figure, format='svg', **kwargs)
    return data_buffer.getvalue()


def render_plot(figure, **kwargs):
    if isinstance(figure, Axes):
        figure = figure.get_figure()
    if "height" in kwargs:
        figure.set_figheight(kwargs["height"])
    if "width" in kwargs:
        figure.set_figwidth(kwargs['width'])
    if kwargs.get("bbox_inches") != 'tight' or kwargs.get("patchless"):
        figure.patch.set_visible(False)
        # figure.axes[0].patch.set_visible(False)
    data_buffer = StringIO()
    figure.savefig(data_buffer, **kwargs)
    plt.close(figure)
    return data_buffer


def rgbpack(color):
    return "rgba(%d,%d,%d,0.5)" % tuple(i * 255 for i in color)


def glycopeptide_string(sequence, long=False, include_glycan=True):
    sequence = PeptideSequence(str(sequence))
    parts = []
    template = "(<span class='modification-chip'"\
        " style='background-color:%s;padding-left:1px;padding-right:2px;border-radius:2px;'"\
        " title='%s' data-modification='%s'>%s</span>)"

    n_term_template = template.replace("(", "").replace(")", "") + '-'
    c_term_template = "-" + (template.replace("(", "").replace(")", ""))

    def render(mod, template=template):
        color = colors.get_color(str(mod))
        letter = escape(mod.name if long else mod.name[0])
        name = escape(mod.name)
        parts.append(template % (rgbpack(color), name, name, letter))

    if sequence.n_term != "H":
        render(sequence.n_term, n_term_template)
    for res, mods in sequence:
        parts.append(res.symbol)
        for mod in mods:
            render(mod)
    if sequence.c_term != "OH":
        render(sequence.c_term, c_term_template)
    parts.append((
        ' ' + glycan_composition_string(str(sequence.glycan)) if sequence.glycan is not None else "")
        if include_glycan else "")
    return ''.join(parts)


def formula(composition):
    return ''.join("<b>%s</b><sub>%d</sub>" % (k, v) for k, v in sorted(composition.items()))


def glycan_composition_string(composition):
    composition = FrozenGlycanComposition.parse(composition)
    parts = []
    template = ("<span class='monosaccharide-name'"
                "style='background-color:%s;padding:2px;border-radius:2px;'>"
                "%s %d</span>")
    for k, v in sorted(composition.items(), key=lambda x: x[0].mass()):
        name = str(k)
        color = colors.get_color(str(name))
        parts.append(template % (rgbpack(color), name, v))
    reduced = composition.reducing_end
    if reduced:
        reducing_end_template = (
            "<span class='monosaccharide-name'"
            "style='background-color:%s;padding:2px;border-radius:2px;'>"
            "%s</span>")
        name = formula(reduced.composition)
        color = colors.get_color(str(name))
        parts.append(reducing_end_template % (rgbpack(color), name))

    return ' '.join(parts)


def highlight_sequence_site(amino_acid_sequence, site_list, site_type_list):
    if isinstance(site_type_list, basestring):
        site_type_list = [site_type_list for i in site_list]
    sequence = list(amino_acid_sequence)
    for site, site_type in zip(site_list, site_type_list):
        sequence[site] = "<span class='{}'>{}</span>".format(site_type, sequence[site])
    return sequence


def n_per_row(sequence, n=60):
    row_buffer = []
    i = 0
    while i < len(sequence):
        row_buffer.append(
            ''.join(sequence[i:(i + n)])
        )
        i += n
    return '<br>'.join(row_buffer)


def prepare_environment(env=None):
    try:
        raise Exception()
        loader = PackageLoader("glycresoft_app", "html")
        loader.list_templates()
    except:
        loader = FileSystemLoader(os.path.join(os.path.dirname(__file__), 'html'))
    if env is None:
        env = Environment(loader=loader)
    else:
        env.loader = loader
    env.fragment_cache = dict()
    env.filters["n_per_row"] = n_per_row
    env.filters['highlight_sequence_site'] = highlight_sequence_site
    env.filters['svg_plot'] = svg_plot
    env.filters['png_plot'] = png_plot
    env.filters['glycopeptide_string'] = glycopeptide_string
    env.filters['glycan_composition_string'] = glycan_composition_string
    env.filters["formula"] = formula
    return env
