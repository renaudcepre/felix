from protest import ProTestSession

from tests.fixtures import neo4j_driver
from tests.unit.test_resolver import resolver_suite
from tests.unit.test_segmenter import segmenter_suite
from tests.unit.test_vectorstore import vectorstore_suite
from tests.integration.test_formatters import formatters_suite
from tests.integration.test_ingest_queries import ingest_queries_suite
from tests.integration.test_profiler_and_repository import profiler_suite
from tests.integration.test_character_crud import character_crud_suite
from tests.integration.test_pipeline import pipeline_suite

session = ProTestSession(concurrency=4, history=True)
session.bind(neo4j_driver)  # SESSION scope — 1 connexion Neo4j

session.add_suite(resolver_suite)
session.add_suite(segmenter_suite)
session.add_suite(vectorstore_suite)
session.add_suite(formatters_suite)
session.add_suite(ingest_queries_suite)
session.add_suite(profiler_suite)
session.add_suite(character_crud_suite)
session.add_suite(pipeline_suite)
