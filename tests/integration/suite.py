from protest import ProTestSuite

from tests.integration.test_formatters import formatters_suite
from tests.integration.test_ingest_queries import ingest_queries_suite
from tests.integration.test_profiler_and_repository import profiler_suite
from tests.integration.test_character_crud import character_crud_suite
from tests.integration.test_pipeline import pipeline_suite

integration_suite = ProTestSuite("Integration", tags=["integration"])
integration_suite.add_suite(formatters_suite)
integration_suite.add_suite(ingest_queries_suite)
integration_suite.add_suite(profiler_suite)
integration_suite.add_suite(character_crud_suite)
integration_suite.add_suite(pipeline_suite)
