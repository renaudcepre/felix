from protest import ProTestSession

from tests.unit.test_conductor import conductor_suite
from tests.unit.test_history_window import history_window_suite
from tests.unit.test_modeling_quality import modeling_quality_suite
from tests.unit.test_recent_entities import recent_entities_suite
from tests.unit.test_relation_typing import relation_typing_suite
from tests.unit.test_resolver import resolver_suite
from tests.unit.test_vectorstore import vectorstore_suite

session = ProTestSession(concurrency=4, history=True)

session.add_suite(resolver_suite)
session.add_suite(vectorstore_suite)
session.add_suite(relation_typing_suite)
session.add_suite(modeling_quality_suite)
session.add_suite(history_window_suite)
session.add_suite(conductor_suite)
session.add_suite(recent_entities_suite)
