from protest import ProTestSession

from tests.unit.test_relation_typing import relation_typing_suite
from tests.unit.test_resolver import resolver_suite
from tests.unit.test_vectorstore import vectorstore_suite

session = ProTestSession(concurrency=4, history=True)

session.add_suite(resolver_suite)
session.add_suite(vectorstore_suite)
session.add_suite(relation_typing_suite)
