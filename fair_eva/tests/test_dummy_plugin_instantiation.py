from fair_eva.api.evaluator import EvaluatorBase


def test_dummy_plugin_instantiates(dummy_plugin):
    assert isinstance(dummy_plugin, EvaluatorBase)
