#!/usr/bin/env python

"""Main simulation runner helpers."""

import sys

import csv

from .language import Language
from .phylo import Phylogeny


def simulate(
        tree, related_concepts, initial_weight,
        concept_weight="degree_squared", scale=1, p_gain=0,
        verbose=False, tips_only=True,
        losswt=lambda x: x,
        related_concepts_edge_weight=lambda x: 0.1*x):
    """Run a phylogeny simulation with the given parameters."""
    phy = Phylogeny(
        related_concepts=related_concepts,
        related_concepts_edge_weight=related_concepts_edge_weight,
        initial_weight=initial_weight,
        basic=[],
        tree=tree,
        losswt=losswt,
        scale=scale)

    for language in phy.simulate(
            concept_weight=concept_weight,
            p_gain=p_gain,
            verbose=verbose):

        dataframe = phy.collect_word_list(
            Language.vocabulary,
            collect_language=language,
            collect_tips_only=tips_only)
        yield dataframe


def write_to_file(columns, dataframe, file=sys.stdout):
    """Write the simulation results to a file object."""
    writer = csv.writer(file)
    writer.writerow(columns)
    writer.writerows(dataframe)
