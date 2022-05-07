# Python 3.8+ required
from __future__ import annotations
from itertools import pairwise
import networkx as nx
from networkx.algorithms import components
import os.path
from typing import Any, BinaryIO, Callable, Iterable, Iterator, TextIO
import warnings


def iter_csv(file: TextIO, /, *, sep: str = ',') -> Iterator[tuple[str, ...]]:
    """Iterate over fields on a CSV file."""
    for line in file:
        fields = (field.strip() for field in line.strip().split(sep))
        fields = tuple(field for field in fields if field)
        if fields:
            yield fields


def read_graph(*, nodes: TextIO, links: TextIO, number: bool = False) -> nx.DiGraph:
    """Read nodes and links from the provided files."""
    graph = nx.DiGraph()

    for name, ident in iter_csv(nodes):
        graph.add_node(ident, label=f'{name} ({ident})' if number else name)

    for id_tail, id_head in iter_csv(links):
        graph.add_edge(id_tail, id_head)

    return nx.freeze(graph)


NAMING_METHODS = {
    'string': 'string',
    'str': 'string',
    's': 'string',
    'initials': 'initials',
    'init': 'initials',
    'ini': 'initials',
    'i': 'initials',
    'cardinal': 'cardinal',
    'card': 'cardinal',
    'c': 'cardinal',
    'ordinal': 'ordinal',
    'ord': 'ordinal',
    'o': 'ordinal',
}

def component_name(graph: nx.DiGraph, num: int, /, *, nodes: Iterable[str], method: str) -> str:
    """Name a component from its index or nodes."""
    method = NAMING_METHODS[method]

    if method == 'string':
        return str(num)
    elif method == 'initials':
        return ''.join(graph.nodes[s]['label'][0] for s in nodes)
    else:
        from num2words import num2words
        return num2words(num + 1, to=method)


def strongly_connected_components(graph: nx.DiGraph, /, *, naming: str):
    """Get components from attributes or using NetworkX's algorithm."""
    output: dict[str, set[str]] = {}

    # extract from attributes, if present
    if (node_component := nx.get_node_attributes(graph, 'component')):
        for node, comp_name in node_component.items():
            comp = output.get(comp_name, set())
            comp.add(node)
            output[comp_name] = comp
    # or calculate components and store in attributes
    else:
        for comp_id, comp_nodes in enumerate(components.strongly_connected_components(graph)):
            comp_name = component_name(graph, comp_id, nodes=comp_nodes, method=naming)
            comp = {node: comp_name for node in comp_nodes}
            nx.set_node_attributes(graph, comp, 'component')
            output[comp_name] = comp_nodes

    return output


# default node layout methods
LAYOUT_METHODS: list[tuple[str, Callable[[nx.DiGraph], dict[str, Any]]]] = [
    ('graphviz', lambda graph: nx.nx_agraph.graphviz_layout(graph, prog='dot')),
    ('kamada_kawai', lambda graph: nx.kamada_kawai_layout(graph)),
    ('spectral', lambda graph: nx.spectral_layout(graph)),
]

def node_layout(graph: nx.DiGraph, /, *, method: str | None = None):
    """Tries to use some advanced methods for node position on drawings."""

    # uses given method
    if method is not None:
        for cur_mehtod, layout in LAYOUT_METHODS:
            if cur_mehtod == method:
                return layout(graph)
        raise ValueError(f"no method named '{method}'")

    # or try every method
    methods = [(f"'{name}'", layout) for name, layout in LAYOUT_METHODS]
    # append a final one for pairwise to work
    methods.append(('no method', lambda _: {}))

    for (cur_method, layout), (next_method, _) in pairwise(methods):
        try:
            return layout(graph)
        except ImportError as error:
            warnings.warn('\n'
                f'Could not use {cur_method} for layout.\n'
                f'Reason: {error}.\n'
                f'Falling back to {next_method}.'
            )
    # no method matched or working
    return None


def node_colors(graph: nx.Graph, /):
    """List the color of each node on `graph` according to its component."""
    from matplotlib import rcParams

    component: dict[str, str] = nx.get_node_attributes(graph, 'component')

    colorlist = [str(c) for c in rcParams['axes.prop_cycle'].by_key()['color']]
    colors = {name: colorlist.pop(0) for name in set(component.values())}

    return tuple(colors[component[node]] for node in graph)


def draw_graph(graph: nx.DiGraph, /, output: BinaryIO | None = None, *, layout: str | None = None):
    """Draw graph and its components using Matplotlib."""
    from matplotlib import pyplot as plt

    position = node_layout(graph, method=layout)
    labels = nx.get_node_attributes(graph, 'label')
    colors = node_colors(graph)
    nx.draw(graph, pos=position, labels=labels, node_color=colors, node_size=1000, font_size=10)

    if output is None:
        plt.show(block=True)
    else:
        plt.savefig(output)


def path_to(filename: str):
    """Relative path to `filename` from current 'scc.py' file."""
    try:
        program = __file__
    # some environemnts (like bpython) don't define '__file__',
    # so we assume that the file is in the current directory
    except NameError:
        return filename

    basedir = os.path.dirname(program)
    fullpath = os.path.join(basedir, filename)
    return os.path.relpath(fullpath)


# Default input files
DEFAULT_NODES = path_to('nodes.csv')
DEFAULT_LINKS = path_to('links.csv')
# Special output modes where no file is generated
NO_OUTPUT = object()
SHOW_OUTPUT = object()


if __name__ == '__main__':
    from argparse import ArgumentParser, FileType

    parser = ArgumentParser('scc.py')
    parser.add_argument('output', nargs='?', type=FileType(mode='wb'), default=None,
        help='GEXF file to be generated with the graph contents.')
    # naming
    parser.add_argument('-num', '--number', default=False, action='store_true',
        help='Add number to node label.')
    parser.add_argument('-n', '--naming', choices=NAMING_METHODS.keys(), default='string',
        metavar='{' + ','.join(set(NAMING_METHODS.values())) + '}',
        help='Method for naming each component according to its index. (default: string)')
    # input file
    parser.add_argument('--nodes', metavar='PATH',
        type=FileType(mode='r', encoding='utf8'), default=DEFAULT_NODES,
        help=f'Path for the \'node.csv\' file. (default: {DEFAULT_NODES})')
    parser.add_argument('--links', metavar='PATH',
        type=FileType(mode='r', encoding='utf8'), default=DEFAULT_LINKS,
        help=f'Path for the \'links.csv\' file. (default: {DEFAULT_LINKS})')
    # drawing
    parser.add_argument('-d', '--draw', metavar='OUTPUT', nargs='?',
        type=FileType(mode='wb'), default=NO_OUTPUT, const=SHOW_OUTPUT,
        help=('Draw NetworkX graph to OUTPUT using Matplotlib. If no argument is provided,'
            ' the graph is drawn on a new window.'))
    parser.add_argument('-l', '--layout', choices=[name for name, _ in LAYOUT_METHODS], default=None,
        help='Method for positioning nodes when draing.')
    args = parser.parse_intermixed_args()

    # reading input
    graph = read_graph(nodes=args.nodes, links=args.links, number=args.number)
    # finding components
    for component, nodes in strongly_connected_components(graph, naming=args.naming).items():
        print(f'{component}:', nodes)
    # writing GEXF
    if args.output is not None:
        nx.write_gexf(graph, args.output)

    # rendering with matplolib
    if args.draw is SHOW_OUTPUT:
        draw_graph(graph, layout=args.layout)
    elif args.draw is not NO_OUTPUT:
        draw_graph(graph, output=args.draw, layout=args.layout)
