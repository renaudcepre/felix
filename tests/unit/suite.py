from protest import ProTestSuite

from tests.unit.test_resolver import resolver_suite
from tests.unit.test_segmenter import segmenter_suite
from tests.unit.test_vectorstore import vectorstore_suite

unit_suite = ProTestSuite("Unit", tags=["unit"])
unit_suite.add_suite(resolver_suite)
unit_suite.add_suite(segmenter_suite)
unit_suite.add_suite(vectorstore_suite)
