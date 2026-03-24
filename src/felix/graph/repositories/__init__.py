"""Neo4j repositories — ré-exports pour compatibilité."""
from felix.graph.repositories.beats import (
    create_narrative_beat,
    link_beat_character,
    list_all_narrative_beats,
)
from felix.graph.repositories.characters import (
    add_character_alias,
    delete_character_relation,
    get_character_fragments,
    get_character_profile,
    get_character_relations,
    get_relation_types_for_pair,
    list_all_character_fragments,
    list_all_character_relations,
    list_all_characters,
    list_all_characters_full,
    overwrite_character_profile_fields,
    patch_character_profile_fields,
    update_character_profile,
    upsert_character_fragment,
    upsert_character_minimal,
    upsert_character_relation,
)
from felix.graph.repositories.groups import (
    create_member_of,
    list_all_groups,
    get_group_detail,
    remove_member_of,
    upsert_group_in_scene,
    upsert_group_minimal,
)
from felix.graph.repositories.issues import (
    create_issue,
    delete_issues_for_scenes,
    get_issue_by_id,
    list_issues,
    update_issue_resolved,
)
from felix.graph.repositories.locations import (
    add_location_alias,
    get_location_detail,
    list_all_locations,
    upsert_location_minimal,
)
from felix.graph.repositories.scenes import (
    count_next_chunk_links_for_stem,
    count_scenes_for_stem,
    get_scene_ids_for_stems,
    get_scene_summaries_by_ids,
    list_all_scenes_full,
    list_scenes,
    upsert_scene,
)
from felix.graph.repositories.timeline import (
    get_timeline_rows,
    list_all_character_events,
    list_all_timeline_events,
    upsert_character_event,
    upsert_timeline_event,
)

__all__ = [
    # characters
    "add_character_alias",
    # locations
    "add_location_alias",
    # scenes
    "count_next_chunk_links_for_stem",
    "count_scenes_for_stem",
    # issues
    "create_issue",
    # groups
    "create_member_of",
    # beats
    "create_narrative_beat",
    "delete_character_relation",
    "delete_issues_for_scenes",
    "get_character_fragments",
    "get_character_profile",
    "get_character_relations",
    "get_group_detail",
    "get_issue_by_id",
    "get_location_detail",
    "get_relation_types_for_pair",
    "get_scene_ids_for_stems",
    "get_scene_summaries_by_ids",
    # timeline
    "get_timeline_rows",
    "link_beat_character",
    "list_all_character_events",
    "list_all_character_fragments",
    "list_all_character_relations",
    "list_all_characters",
    "list_all_characters_full",
    "list_all_groups",
    "list_all_locations",
    "list_all_narrative_beats",
    "list_all_scenes_full",
    "list_all_timeline_events",
    "list_issues",
    "list_scenes",
    "overwrite_character_profile_fields",
    "remove_member_of",
    "patch_character_profile_fields",
    "update_character_profile",
    "update_issue_resolved",
    "upsert_character_event",
    "upsert_character_fragment",
    "upsert_character_minimal",
    "upsert_character_relation",
    "upsert_group_in_scene",
    "upsert_group_minimal",
    "upsert_location_minimal",
    "upsert_scene",
    "upsert_timeline_event",
]
