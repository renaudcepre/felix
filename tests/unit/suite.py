from protest import ProTestSuite

from tests.unit.test_modeling_quality import modeling_quality_suite
from tests.unit.test_relation_typing import relation_typing_suite
from tests.unit.test_resolver import resolver_suite
from tests.unit.test_vectorstore import vectorstore_suite

unit_suite = ProTestSuite("Unit", tags=["unit"])
unit_suite.add_suite(resolver_suite)
unit_suite.add_suite(vectorstore_suite)
unit_suite.add_suite(relation_typing_suite)
unit_suite.add_suite(modeling_quality_suite)
