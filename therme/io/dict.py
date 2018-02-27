# -*- coding: utf-8 -*-
"""
.. module:: pytfa
   :platform: Unix, Windows
   :synopsis: Thermodynamics-based Flux Analysis

.. moduleauthor:: pyTFA team

Make the model serializable
"""
from collections import OrderedDict, defaultdict
import cobra.io.dict as cbd
from cobra.exceptions import SolverNotFound

from ..thermo.tmodel import ThermoModel
from ..me.base import MEModel
from ..fusion.thermome import ThermoMEModel
from ..me.utils import replace_by_enzymatic_reaction, replace_by_translation_reaction
from ..me.reaction import TranslationReaction, EnzymaticReaction
from ..me.enzyme import Enzyme, Ribosome, Peptide
from ..me.optim import  EnzymeConstraint, GeneVariable, ModelConstraint, ModelVariable
from ..optim.variables import ReactionVariable, MetaboliteVariable
from ..optim.constraints import ReactionConstraint, MetaboliteConstraint

from optlang.util import expr_to_json, parse_expr


def get_all_subclasses(cls):
    all_subclasses = []

    for subclass in cls.__subclasses__():
        all_subclasses.append(subclass)
        all_subclasses.extend(get_all_subclasses(subclass))

    return all_subclasses

def make_subclasses_dict(cls):
    the_dict = {x.__name__:x for x in get_all_subclasses(cls)}
    the_dict[cls.__name__] = cls
    return the_dict

REACTION_VARIABLE_SUBCLASSES    = make_subclasses_dict(ReactionVariable)
REACTION_CONSTRAINT_SUBCLASSES  = make_subclasses_dict(ReactionConstraint)
METABOLITE_VARIABLE_SUBCLASSES  = make_subclasses_dict(MetaboliteVariable)
METABOLITE_CONSTRAINT_SUBCLASSES= make_subclasses_dict(MetaboliteConstraint)
ENZYME_VARIABLE_SUBCLASSES      = make_subclasses_dict(GeneVariable)
ENZYME_CONSTRAINT_SUBCLASSES    = make_subclasses_dict(EnzymeConstraint)
MODEL_VARIABLE_SUBCLASSES       = make_subclasses_dict(ModelVariable)
MODEL_CONSTRAINT_SUBCLASSES     = make_subclasses_dict(ModelConstraint)

SOLVER_DICT = {
    'optlang.gurobi_interface':'optlang-gurobi',
    'optlang.cplex_interface':'optlang-cplex',
    'optlang.glpk_interface':'optlang-glpk',
}

def metabolite_thermo_to_dict(metthermo):
    return metthermo.thermo.__dict__

def enzyme_to_dict(enzyme):
    obj = OrderedDict()
    obj['id'] = enzyme.id
    obj['name'] = enzyme.name
    obj['kcat'] = enzyme.kcat
    obj['kdeg'] = enzyme.kdeg
    obj['varname'] = enzyme.variable.name
    return obj

def ribosome_to_dict(ribosome):
    obj = OrderedDict()
    obj['id'] = ribosome.id
    obj['name'] = ribosome.name
    obj['kribo'] = ribosome.kribo
    obj['kdeg'] = ribosome.kdeg
    obj['varname'] = ribosome.variable.name
    return obj

def var_to_dict(variable):
    obj = OrderedDict()
    obj['id'] = variable.id
    obj['name'] = variable.name
    obj['kind'] = type(variable).__name__
    obj['lb'] = variable.variable.lb
    obj['ub'] = variable.variable.ub
    obj['type'] = variable.type
    return obj

def cons_to_dict(constraint):
    obj = OrderedDict()
    obj['id'] = constraint.id
    obj['name'] = constraint.name
    obj['kind'] = type(constraint).__name__
    obj['lb'] = constraint.constraint.lb
    obj['ub'] = constraint.constraint.ub
    # obj['expression'] = str(constraint.expr)
    obj['expression'] = expr_to_json(constraint.expr)
    return obj

def archive_variables(var_dict):
    obj = OrderedDict()

    obj['variables'] = []
    for classname,variables in var_dict.items():
        obj[classname] = list(map(var_to_dict, variables))

    return obj

def archive_constraints(cons_dict):
    obj = OrderedDict()

    for classname,constraints in cons_dict.items():
        obj[classname] = list(map(cons_to_dict, constraints))

    return obj

def archive_compositions(compositions):
    """
    Turns a peptide compositions dict of the form:
    { 'b3991': defaultdict(int,
             {<Metabolite ala__L_c at 0x7f7d25504f28>: -42,
              <Metabolite arg__L_c at 0x7f7d2550bcf8>: -11,
              <Metabolite asn__L_c at 0x7f7d2550beb8>: -6,
              ...}),
    ...}


    to:

    { 'b3991': defaultdict(int,,
            {'ala__L_c': -42,
             'arg__L_c': -11,
             'asn__L_c': -6,
              ...}),
    ...}
    :param compositions:
    :return:
    """
    obj = {}
    for k, stoich in compositions.items():
        obj[k] = _stoichiometry_to_dict(stoich)

    return obj

def _stoichiometry_to_dict(stoichiometric_dict):
    """
    Turns a stoichiometric compositions dict of the form:
    'b3991': defaultdict(int,
           {<Metabolite ala__L_c at 0x7f7d25504f28>: -42,
            <Metabolite arg__L_c at 0x7f7d2550bcf8>: -11,
            <Metabolite asn__L_c at 0x7f7d2550beb8>: -6,
            ...})

    to:

    'b3991': defaultdict(int,,
            {'ala__L_c': -42,
             'arg__L_c': -11,
             'asn__L_c': -6,
              ...})
    """
    return defaultdict(int, {k.id:v for k,v in stoichiometric_dict.items()})

def archive_coupling_dict(coupling_dict):
    """
    Turns an enzyme coupling dict of the form:

    {'AB6PGH': <Enzyme AB6PGH at 0x7f7d1371add8>,
     'ABTA': <Enzyme ABTA at 0x7f7d1371ae48>,
     'ACALD': <Enzyme ACALD at 0x7f7d1371aeb8>}

    to:
    {'AB6PGH': 'AB6PGH',
     'ABTA': 'ABTA',
     'ACALD': 'ACALD'
    """
    return {k:v.id for k,v in coupling_dict.items()}

def get_solver_string(model):
    return SOLVER_DICT[model.solver.__class__.__module__]


def model_to_dict(model):
    """

    :param model:
    :return:
    """

    # Take advantage of cobra's dict serialization for metabolites and
    # reactions
    obj = cbd.model_to_dict(model)

    obj['solver'] = get_solver_string(model)

    # Copy variables, constraints
    # obj['var_dict'] = archive_variables(model._var_kinds)
    # obj['cons_dict'] = archive_constraints(model._cons_kinds)
    obj['variables'] = list(map(var_to_dict, model._var_dict.values()))
    obj['constraints'] = list(map(cons_to_dict, model._cons_dict.values()))

    is_thermo = False
    is_me = False

    if isinstance(model, ThermoModel):
        obj['kind'] = 'ThermoModel'
        obj['thermo_data'] = model.thermo_data #it's a dict
        obj['name'] = model.name
        obj['temperature'] = model.TEMPERATURE
        obj['min_ph'] = model.MIN_pH
        obj['max_ph'] = model.MAX_pH
        is_thermo = True

    if isinstance(model, MEModel):

        # Convenience attributes
        # obj['_mu'] = model.mu.name
        obj['compositions'] = archive_compositions(model.compositions)
        obj['coupling_dict'] = archive_coupling_dict(model.coupling_dict)
        obj['mu_bins'] = model.mu_bins

        # Growth
        obj['growth_reaction'] = model.growth_reaction.id

        # Enzymes
        obj['max_enzyme_concentration'] = model.max_enzyme_concentration
        obj['enzymes'] = list(map(enzyme_to_dict, model.enzymes))

        # Ribosome
        obj['ribosome'] = ribosome_to_dict(model.ribosome)
        obj['kind'] = 'MEModel'
        is_me = True

    if isinstance(model, ThermoMEModel):
        obj['kind'] = 'ThermoMEModel'


    # Metabolite and Reaction-level cleanup

    for rxn_dict in obj['reactions']:
        rxn = model.reactions.get_by_id(rxn_dict['id'])

        if is_me:
            _add_me_reaction_info(rxn, rxn_dict)

        if is_thermo:
            _add_thermo_reaction_info(rxn, rxn_dict)


    # Peptides and Thermo
    for met_dict in obj['metabolites']:
        the_met_id = met_dict['id']
        is_peptide = False

        if is_me:
            if the_met_id in model.peptides:
                met_dict['kind'] = 'Peptide'
                is_peptide = True

        if is_thermo and not is_peptide: # peptides have no thermo
            the_met = model.metabolites.get_by_id(the_met_id)
            _add_thermo_metabolite_info(the_met, rxn_dict)
            met_dict['kind'] = 'Metabolite'

    return obj

def _add_me_reaction_info(rxn, rxn_dict):
    # We start with translation reactions because they are also
    # enzymatic reactions
    # Translation Reactions
    if isinstance(rxn, TranslationReaction):
        rxn_dict['kind'] = 'TranslationReaction'
    # Enzymatic Reactions
    elif isinstance(rxn, EnzymaticReaction):
        rxn_dict['kind'] = 'EnzymaticReaction'
        rxn_dict['enzymes'] = [x.id for x in rxn.enzymes]
    # Generic Reaction
    else:
        rxn_dict['kind'] = 'Reaction'

def _add_thermo_reaction_info(rxn, rxn_dict):
    if hasattr(rxn, 'thermo'):
        rxn_dict['thermo'] = rxn.thermo

def _add_thermo_metabolite_info(met, met_dict):
    if hasattr(met, 'thermo'):
        met_dict['thermo'] = metabolite_thermo_to_dict(met)

def model_from_dict(obj, solver=None):
    # Take advantage of cobra's serialization of mets and reactions
    new = cbd.model_from_dict(obj)

    if solver is not None:
        try:
            new.solver = solver
        except SolverNotFound as snf:
            raise snf
    else:
        try:
            new.solver = obj['solver']
        except KeyError:
            pass

    # Populate variables and constraints
    if obj['kind'] == 'ThermoMEModel':
        new = ThermoMEModel(thermo_data=obj['thermo_data'],
                            model=new,
                            name=obj['name'],
                            temperature=obj['temperature'],
                            min_ph=obj['min_ph'],
                            max_ph=obj['max_ph'])
        new = init_thermo_me_model_from_dict(new, obj)
    elif obj['kind'] == 'MEModel':
        # Cast to MEModel
        new = MEModel(new)
        new = init_me_model_from_dict(new, obj)
    elif obj['kind'] == 'ThermoModel':
        new = ThermoModel(thermo_data=obj['thermo_data'],
                          model=new,
                          name=obj['name'],
                          temperature=obj['temperature'],
                          min_ph=obj['min_ph'],
                          max_ph=obj['max_ph'])
        new = init_thermo_model_from_dict(new, obj)

    new._update()

    for the_var_dict in obj['variables']:
        this_id = the_var_dict['id']
        classname = the_var_dict['kind']
        lb = the_var_dict['lb']
        ub = the_var_dict['ub']

        if classname in REACTION_VARIABLE_SUBCLASSES:
            hook = new.reactions.get_by_id(this_id)
            this_class = REACTION_VARIABLE_SUBCLASSES[classname]
            nv = new.add_variable(kind=this_class,
                                  hook=hook,
                                  ub = ub,
                                  lb = lb,
                                  queue=True)

        elif classname in METABOLITE_VARIABLE_SUBCLASSES:
            hook = new.metabolites.get_by_id(this_id)
            this_class = METABOLITE_VARIABLE_SUBCLASSES[classname]
            nv = new.add_variable(kind=this_class,
                                  hook=hook,
                                  ub = ub,
                                  lb = lb,
                                  queue=True)

        elif classname in ENZYME_VARIABLE_SUBCLASSES:
            hook = new.enzymes.get_by_id(this_id)
            this_class = ENZYME_VARIABLE_SUBCLASSES[classname]
            nv = new.add_variable(kind=this_class,
                                  hook=hook,
                                  ub = ub,
                                  lb = lb,
                                  queue=True)

        elif classname in MODEL_VARIABLE_SUBCLASSES:
            hook = new
            this_class = MODEL_VARIABLE_SUBCLASSES[classname]
            nv = new.add_variable(kind=this_class,
                                  hook=hook,
                                  id_ = this_id,
                                  ub = ub,
                                  lb = lb,
                                  queue=True)

        else:
            raise TypeError(
                'Class {} serialization not handled yet' \
                    .format(classname))

    new._update()

    variable_parse_dict = {x.name:x for x in new.variables}

    for the_cons_dict in obj['constraints']:
        this_id = the_cons_dict['id']
        classname = the_cons_dict['kind']
        new_expr = parse_expr(the_cons_dict['expression'],
                              local_dict = variable_parse_dict)
        # str_expr = the_cons_dict['expression']
        #
        # # Sympify the expression so that we can substitute variables afterwards
        # sym_expr = sympify(str_expr)
        #
        # subs_dict = {x:new.variables.get(x.name) for x in sym_expr.free_symbols}
        #
        # new_expr = sym_expr.subs(subs_dict)
        lb = the_cons_dict['lb']
        ub = the_cons_dict['ub']

        if classname in REACTION_CONSTRAINT_SUBCLASSES:
            hook = new.reactions.get_by_id(this_id)
            this_class = REACTION_CONSTRAINT_SUBCLASSES[classname]
            nc = new.add_constraint(kind=this_class, hook=hook,
                                    expr=new_expr,
                                    ub = ub,
                                    lb = lb,
                                    queue=True)

        elif classname in METABOLITE_CONSTRAINT_SUBCLASSES:
            hook = new.metabolites.get_by_id(this_id)
            this_class = METABOLITE_CONSTRAINT_SUBCLASSES[classname]
            nc = new.add_constraint(kind=this_class, hook=hook,
                                    expr=new_expr,
                                    ub = ub,
                                    lb = lb,
                                    queue=True)

        elif classname in ENZYME_CONSTRAINT_SUBCLASSES:
            hook = new.enzymes.get_by_id(this_id)
            this_class = ENZYME_CONSTRAINT_SUBCLASSES[classname]
            nc = new.add_constraint(kind=this_class, hook=hook,
                                    expr=new_expr,
                                    ub = ub,
                                    lb = lb,
                                    queue=True)

        elif classname in MODEL_CONSTRAINT_SUBCLASSES:
            hook=new
            this_class = MODEL_CONSTRAINT_SUBCLASSES[classname]
            nc = new.add_constraint(kind=this_class, hook=hook,
                                    expr=new_expr, id_ = this_id,
                                    ub = ub,
                                    lb = lb,
                                    queue=True)
        else:
            raise TypeError('Class {} serialization not handled yet' \
                            .format(classname))

    new._update()
    new.repair()
    return new

def init_me_model_from_dict(new, obj):
    new.max_enzyme_concentration = obj['max_enzyme_concentration']

    # Convenience attributes
    # new._mu = new.variables.get(obj['_mu'])
    new.compositions = rebuild_compositions(new, obj['compositions'])
    new.mu_bins = obj['mu_bins']

    # Add growth reaction
    new.growth_reaction = obj['growth_reaction']

    # Populate enzymes
    new.add_enzymes([enzyme_from_dict(x) for x in obj['enzymes']])
    new.coupling_dict = rebuild_coupling_dict(new, obj['coupling_dict'])

    # Make ribosome
    new_ribosome = ribosome_from_dict(obj['ribosome'])
    new_ribosome._model = new
    new.enzymes._replace_on_id(new_ribosome)
    new.ribosome = new_ribosome
    new.ribosome.init_variable()
    new.init_ribosome_variables()

    # Populate EnzymaticReaction and TranslationReaction
    find_enzymatic_reactions_from_dict(new, obj)
    find_translation_reactions_from_dict(new, obj)

    # Populate Peptides
    find_peptides_from_dict(new, obj)

    return new

def init_thermo_model_from_dict(new, obj):
    for rxn_dict in obj['reactions']:
        rxn = new.reactions.get_by_id(rxn_dict['id'])

        if 'thermo' in rxn_dict:
            rxn.thermo = rxn_dict['thermo']

    for met_dict in obj['metabolites']:
        met = new.metabolites.get_by_id(met_dict['id'])

        if 'thermo' in met_dict:
            new._prepare_metabolite(met)
    return new


def init_thermo_me_model_from_dict(new, obj):
    new = init_thermo_model_from_dict(new, obj)
    new = init_me_model_from_dict(new,obj)
    return new

def rebuild_compositions(new, compositions_dict):
    """
    Performs the reverse operation of :func:archive_compositions

    :param new:
    :param compositions_dict:
    :return:
    """

    return {k:_rebuild_stoichiometry(new,stoich)
            for k,stoich in compositions_dict.items()}

def _rebuild_stoichiometry(new, stoich):
    """
    Performs the reverse operation of :func:_stoichiometry_to_dict

    :param new:
    :param stoich:
    :return:
    """

    return defaultdict(int,
                       {new.metabolites.get_by_id(k):v
                        for k,v in stoich.items()})

def rebuild_coupling_dict(new, coupling_dict):
    """
    Performs the reverse operation of :func:archive_coupling_dict

    :param new:
    :param coupling_dict:
    :return:
    """
    return {k:new.enzymes.get_by_id(v) for k,v in coupling_dict.items()}

def enzyme_from_dict(obj):
    return Enzyme(id = obj['id'],
                  kcat = obj['kcat'],
                  kdeg = obj['kdeg'])


def ribosome_from_dict(obj):
    return  Ribosome( id = obj['id'],
                      kribo = obj['kribo'],
                      kdeg = obj['kdeg'])

def find_enzymatic_reactions_from_dict(new, obj):
    for rxn_dict in obj['reactions']:
        if rxn_dict['kind'] == 'EnzymaticReaction':
            enzymes = [new.enzymes.get_by_id(x) for x in rxn_dict['enzymes']]
            replace_by_enzymatic_reaction(new, rxn_dict['id'], enzymes)


def find_translation_reactions_from_dict(new, obj):
    new_transl_rxns = list()
    for rxn_dict in obj['reactions']:
        if rxn_dict['kind'] == 'TranslationReaction':
            enzymes = new.ribosome
            enz_rxn = replace_by_translation_reaction(new, rxn_dict['id'], enzymes)
            new_transl_rxns.append(enz_rxn)
    new.translation_reactions += new_transl_rxns

def find_peptides_from_dict(new, obj):
    new_peptides = list()
    for met_dict in obj['metabolites']:
        if met_dict['kind'] == 'Peptide':
            met = new.metabolites.get_by_id(met_dict['id'])
            pep = Peptide.from_metabolite(met)
            new.metabolites._replace_on_id(pep)
            new_peptides.append(pep)
    new.peptides += new_peptides

