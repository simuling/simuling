#!/usr/bin/env python
"""Simulate lexical evolution based on gradual semantic shift.

"""

import bisect
import collections
import numpy.random as random

import networkx

import argparse


class SemanticNetwork (networkx.Graph):
    """A network describing relations between concepts.

    In addition to usual graph methods, the semantic network provides
    easy generation of random concepts.

    """
    def __init__(self, *args, neighbor_factor=0.004, **kwargs):
        super().__init__(*args, **kwargs)
        self.neighbor_factor = neighbor_factor

    @classmethod
    def load_from_gml(cls, lines, weight_attribute):
        related_concepts = networkx.parse_gml(lines)
        network = cls(related_concepts)
        network.weight_attribute = weight_attribute
        return network

    def edge_weight(self, original_meaning, connected_meaning):
        try:
            edge_properties = self[original_meaning][connected_meaning]
        except KeyError:
            # No such edge.
            return 0
        try:
            raw_weight = edge_properties[self.weight_attribute]
        except KeyError:
            raw_weight = 1
        return self.neighbor_factor * raw_weight

    def concept_weight(self, concept):
        return len(self[concept]) ** 2

    def random(self, random=random):
        try:
            max_heap = self._heap[-1]
        except AttributeError:
            self._heap = []
            max_heap = 0
            for concept in self.nodes():
                max_heap += self.concept_weight(concept)
                self._heap.append(max_heap)
        index = bisect.bisect(self._heap,
                              random.random() * max_heap)
        return self.nodes()[index]


class WeightedBipartiteGraph (dict):
    """A weighted, bipartite graph

    This is the general case of the objects we use to implement
    languages

    """
    def __missing__(self, key):
        self[key] = collections.defaultdict(lambda: 0)
        return self[key]

    def add_edge(self, left, right, weight):
        self[left][right] = weight


class Language (WeightedBipartiteGraph):
    max_word = 0

    def __init__(self, dictionary, semantics):
        super().__init__(dictionary)
        self.semantics = semantics

    def weighted_neighbors(self, concept):
        weights = {
            x: self.semantics.edge_weight(concept, x)
            for x in self.semantics[concept]}
        weights[concept] = 1
        return weights

    def calculate_scores(self, concept):
        score = {}
        for s_concept, s_weight in self.weighted_neighbors(concept).items():
            for word, weight in self[s_concept].items():
                if weight > 0:
                    score.setdefault(word, 0)
                    score[word] += weight * s_weight
        return score

    def random_edge(self, random=random):
        weights = []
        edges = []
        max_weight = 0
        for concept, words in self.items():
            for word, weight in words.items():
                if weight > 0:
                    edges.append((concept, word))
                    max_weight += weight
                    weights.append(max_weight)
        index = bisect.bisect(weights, random.random() * max_weight)
        return edges[index]

    def step(self):
        # Choose v_0
        concept_1 = self.semantics.random()
        # Choose v_1
        concept_2 = self.semantics.random()
        while concept_1 == concept_2:
            concept_2 = self.semantics.random()
        # Calculate scores x_w0 for v_0
        neighbors_1 = self.calculate_scores(concept_1)
        # Calculate scores x_w1 for v_1
        neighbors_2 = self.calculate_scores(concept_2)
        # Generate R_0
        words_for_c1_only = set(neighbors_1) - set(neighbors_2)
        # Adapt the language
        if words_for_c1_only:
            incumbent = max(words_for_c1_only, key=neighbors_1.get)
            self[concept_1][incumbent] += 1
        else:
            self.add_edge(concept_1, Language.max_word, 1)
            Language.max_word += 1
        # Generate R_1
        words_for_c2_only = set(neighbors_2) - set(neighbors_1)
        # Adapt the language
        if words_for_c2_only:
            incumbent = max(words_for_c2_only, key=neighbors_2.get)
            self[concept_2][incumbent] += 1
        else:
            self.add_edge(concept_2, Language.max_word, 1)
            Language.max_word += 1

        # Reduce confusing word.
        all_neighbors = self.weighted_neighbors(concept_1)
        for neighbor, wt in self.weighted_neighbors(concept_2).items():
            all_neighbors[neighbor] = all_neighbors.get(neighbor, 0) + wt

        confusing_weight = 0
        for word, weight in neighbors_1.items():
            if word in neighbors_2:
                for target, wt in all_neighbors.items():
                    weight = self[target][word] * wt
                    if weight > confusing_weight:
                        confusing_word = word
                        confusing_meaning = target
                        confusing_weight = weight
        if confusing_weight:
            self[confusing_meaning][confusing_word] -= 1
            if self[confusing_meaning][confusing_word] <= 0:
                del self[confusing_meaning][confusing_word]
        else:
            concept, word = self.random_edge()
            self[concept][word] -= 1
            if self[concept][word] <= 0:
                del self[concept][word]

        # Remove a unit of weight.
        concept, word = self.random_edge()
        self[concept][word] -= 1
        if self[concept][word] <= 0:
            del self[concept][word]

    def __str__(self):
        return ",\n".join([
            "{:}: {{{:}}}".format(
                c,
                ", ".join(
                    ["{:}: {:}".format(w, wt)
                     for w, wt in ws.items()
                     if wt > 0]))
            for c, ws in self.items()
            if ws])

    def copy(self):
        return Language(
            {concept: collections.defaultdict(
                (lambda: 0),
                {word: weight
                 for word, weight in words.items()})
             for concept, words in self.items()},
            self.semantics)


def simulate(phylogeny, language):
    """Run a simulation of a root language down a phylogeny"""
    if phylogeny.name:
        yield (phylogeny.name, language)
    for i in range(int(phylogeny.length)):
        language.step()
    for child in phylogeny.descendants:
        for (name, language) in simulate(child, language.copy()):
            yield (name, language)


def parse_distribution_description(text, random=random):
    try:
        name, parameters = text.strip().split("(")
    except ValueError:
        const = int(text.strip())
        return lambda: const
    if not parameters.endswith(")"):
        raise ValueError("Could not parse distribution string")
    function = {
        "uniform": lambda x: random.randint(1, x),
        "constant": lambda x: x,
        "geometric": lambda x: random.geometric(1 / x),
        "poisson": lambda x: random.poisson(x)}[name]
    args = [int(x) for x in parameters.split(",")]
    return lambda: function(args)


def argparser():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    initialization = parser.add_argument_group(
        "Initializing the root language")
    initialization.add_argument(
        "--wordlist", type=argparse.FileType("r"),
        help="Load the root language from this CLDF Wordlist. (default: Create"
        " a new language with exactly one word for each concept.)")
    initialization.add_argument(
        "--language",
        help="Load this Language_ID from the CLDF Wordlist. (default: The one"
        " referred to in the last line of the table with the Cognateset_IDs.)")
    initialization.add_argument(
        "--weight",
        default="100",
        help="Random distribution to use when initializing the root language,"
        " if no weights are given in the CLDF Wordlist. (default: The"
        " distribution that always returns 100.)")
    parameters = parser.add_argument_group(
        "Simulation parameters")
    parameters.add_argument(
        "--semantic-network", type=argparse.FileType("r"),
        help="The semantic network, given as GML file. (default: CLICS.)")
    parameters.add_argument(
        "--neighbor-factor", type=float,
        default=0.004,
        help="The connection strength between adjacent concepts of edge weight"
        " 1 in the semantic network. (default: 0.004)")
    parameters.add_argument(
        "--weight-attribute",
        default="FamilyWeight",
        help="The GML edge attribute to be used as edge weight."
        " (default: FamilyWeight.)")
    parameters.add_argument(
        "--seed", type=int,
        default=0,
        help="The random number generator seed (default: 0)")
    tree = parser.add_argument_group(
        "Shape of the phylogeny")
    tree.add_argument(
        "--tree",
        help="A phylogenetic tree to be simulated in Newick format, or the"
        " path to an existing file containing such a tree. (default: A single"
        " long branch with nodes after 0, 1, 2, 4, 8, …, 2^N time steps.)")
    tree.add_argument(
        "--branchlength", type=int,
        default=20,
        help="If no tree is given, the log₂ of the maximum branch length"
        " of the long branch, i.e. N from the default value above."
        " (default: 20.)")
    output = parser.add_argument_group(
        "Output")
    output.add_argument(
        "--output-file", type=argparse.FileType("w"),
        default="tmp",
        help="The file to write output data to (in CLDF-like CSV)."
        " (default: A temporary file.)")
    output.add_argument(
        "--embed-parameters", action="store_true",
        default=False,
        help="Echo the simulation parameters to comments in the CSV output"
        " file.")
    return parser


def echo(args):
    for arg, value in args.__dict__.items():
        if arg == "embed_parameters":
            continue
        if value is not None:
            try:
                value = value.name
            except AttributeError:
                pass
            yield arg, value
