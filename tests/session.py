from protest import ProTestSession

from tests.unit.test_alerts import alerts_suite
from tests.unit.test_backoff import backoff_suite
from tests.unit.test_conductor import conductor_suite
from tests.unit.test_cost import cost_suite
from tests.unit.test_emergent_profile import emergent_profile_suite
from tests.unit.test_entity_list_summary import entity_list_summary_suite
from tests.unit.test_event_reorder import event_reorder_suite
from tests.unit.test_history_window import history_window_suite
from tests.unit.test_ingest_document import ingest_document_suite
from tests.unit.test_llm_timeout import llm_timeout_suite
from tests.unit.test_maintenance_profile import maintenance_profile_suite
from tests.unit.test_modeling_quality import modeling_quality_suite
from tests.unit.test_profile_evolution import profile_evolution_suite
from tests.unit.test_profile_store import profile_store_suite
from tests.unit.test_project_scoping import project_scoping_suite
from tests.unit.test_recent_entities import recent_entities_suite
from tests.unit.test_refusal_terminal import refusal_terminal_suite
from tests.unit.test_relation_reemission import relation_reemission_suite
from tests.unit.test_relation_typing import relation_typing_suite
from tests.unit.test_resolver import resolver_suite
from tests.unit.test_retype_entity import retype_entity_suite
from tests.unit.test_schema_changes import schema_changes_suite
from tests.unit.test_schema_detector import schema_detector_suite
from tests.unit.test_source_pages import source_pages_suite
from tests.unit.test_source_verify import source_verify_suite
from tests.unit.test_synthetic_parc import synthetic_parc_suite
from tests.unit.test_tool_labels import tool_labels_suite
from tests.unit.test_tool_trace import tool_trace_suite
from tests.unit.test_update_entity_changes import update_entity_changes_suite
from tests.unit.test_update_event_guard import update_event_guard_suite
from tests.unit.test_user_edits import user_edits_suite
from tests.unit.test_vectorstore import vectorstore_suite

session = ProTestSession(concurrency=4, history=True)

session.add_suite(alerts_suite)
session.add_suite(backoff_suite)
session.add_suite(resolver_suite)
session.add_suite(vectorstore_suite)
session.add_suite(relation_typing_suite)
session.add_suite(modeling_quality_suite)
session.add_suite(history_window_suite)
session.add_suite(conductor_suite)
session.add_suite(recent_entities_suite)
session.add_suite(user_edits_suite)
session.add_suite(refusal_terminal_suite)
session.add_suite(update_event_guard_suite)
session.add_suite(project_scoping_suite)
session.add_suite(llm_timeout_suite)
session.add_suite(event_reorder_suite)
session.add_suite(relation_reemission_suite)
session.add_suite(retype_entity_suite)
session.add_suite(schema_changes_suite)
session.add_suite(maintenance_profile_suite)
session.add_suite(ingest_document_suite)
session.add_suite(emergent_profile_suite)
session.add_suite(profile_store_suite)
session.add_suite(profile_evolution_suite)
session.add_suite(schema_detector_suite)
session.add_suite(cost_suite)
session.add_suite(source_pages_suite)
session.add_suite(source_verify_suite)
session.add_suite(entity_list_summary_suite)
session.add_suite(update_entity_changes_suite)
session.add_suite(tool_labels_suite)
session.add_suite(tool_trace_suite)
session.add_suite(synthetic_parc_suite)
