"""Tests for prompt memory injection (Phase 2 feature).

Verifies that:
1. format_social_memory produces correct output for various inputs
2. Discussion prompts accept and render memory blocks
3. Ask NPC context includes peer warnings
4. Concern events carry source details for persistence
"""

from backend.llm.prompts import (
    DISCUSSION_USER,
    format_social_memory,
    format_ask_npc_system,
)
from backend.simulation.npc import (
    DiscussionMemory,
    NpcState,
    PeerWarning,
)


# ---------------------------------------------------------------------------
# format_social_memory
# ---------------------------------------------------------------------------

def test_format_social_memory_with_dataclasses():
    """PeerWarning and DiscussionMemory dataclasses render correctly."""
    warnings = [
        PeerWarning(
            tick=2, source_id="npc1", source_name="Alex",
            source_archetype="analytical_skeptic", theme="price",
            content="Too expensive for what it does", delta=-0.05,
        ),
    ]
    discussions = [
        DiscussionMemory(
            tick=3, partner_id="npc2", partner_name="Jordan",
            key_point="AI claims are unproven", my_delta=-0.08,
        ),
    ]
    result = format_social_memory(warnings, discussions, ["price", "evidence"])

    assert "Alex" in result
    assert "price" in result
    assert "Too expensive" in result
    assert "Jordan" in result
    assert "AI claims are unproven" in result
    assert "price, evidence" in result


def test_format_social_memory_with_dicts():
    """Dict inputs (from API/event reconstruction) also work."""
    warnings = [
        {"tick": 2, "source_name": "Carol", "theme": "ethics",
         "content": "No sustainability info", "delta": -0.03},
    ]
    result = format_social_memory(warnings, [], None)

    assert "Carol" in result
    assert "ethics" in result
    assert "No sustainability info" in result


def test_format_social_memory_empty():
    """Empty memories return empty string (no noise in prompts)."""
    assert format_social_memory([], [], []) == ""
    assert format_social_memory([], [], None) == ""


def test_format_social_memory_truncates_long_content():
    """Content over 120 chars gets truncated."""
    warnings = [
        PeerWarning(
            tick=1, source_id="x", source_name="X",
            source_archetype="a", theme="price",
            content="A" * 200, delta=-0.01,
        ),
    ]
    result = format_social_memory(warnings, [], [])
    assert "..." in result
    assert "A" * 200 not in result


def test_format_social_memory_discussion_direction():
    """Positive deltas say 'raised', negative say 'lowered'."""
    pos = [DiscussionMemory(tick=1, partner_id="x", partner_name="X",
                            key_point="good point", my_delta=0.05)]
    neg = [DiscussionMemory(tick=1, partner_id="y", partner_name="Y",
                            key_point="bad point", my_delta=-0.05)]

    pos_result = format_social_memory([], pos, [])
    neg_result = format_social_memory([], neg, [])

    assert "raised" in pos_result
    assert "lowered" in neg_result


# ---------------------------------------------------------------------------
# Discussion prompt integration
# ---------------------------------------------------------------------------

def test_discussion_prompt_renders_with_memory():
    """DISCUSSION_USER accepts memory_a and memory_b placeholders."""
    prompt = DISCUSSION_USER.format(
        idea_title="Test", idea_description="A test",
        persona_a="Alice", persona_b="Bob",
        stance_a="skeptical", interest_a=0.3,
        stance_b="interested", interest_b=0.7,
        trust_level=0.6,
        memory_a="What you've heard: Alex warned about price",
        memory_b="",
    )
    assert "Alex warned about price" in prompt
    assert "Person A" in prompt
    assert "Person B" in prompt


def test_discussion_prompt_renders_without_memory():
    """Empty memory strings don't break the prompt."""
    prompt = DISCUSSION_USER.format(
        idea_title="Test", idea_description="A test",
        persona_a="Alice", persona_b="Bob",
        stance_a="neutral", interest_a=0.5,
        stance_b="neutral", interest_b=0.5,
        trust_level=0.5,
        memory_a="", memory_b="",
    )
    assert "Person A" in prompt
    assert "Person B" in prompt
    # No memory noise
    assert "heard from" not in prompt.lower()


# ---------------------------------------------------------------------------
# Ask NPC context with peer warnings
# ---------------------------------------------------------------------------

def test_ask_npc_includes_peer_warnings():
    """format_ask_npc_system renders peer warnings section."""
    ctx = {
        "npc_profile": {
            "name": "Alice", "age": 30, "occupation": "Designer",
            "income_level": "middle", "communication_style": "direct",
            "personality": {"openness": 0.7, "skepticism": 0.5},
            "interests": ["design"], "values": ["creativity"],
            "pain_points": ["time"],
        },
        "idea": {
            "title": "TestApp", "description": "An app",
            "category": "mobile_app", "target_audience": "designers",
            "price_point": "$10/month",
        },
        "current_state": {
            "stance": "skeptical", "interest_score": 0.3,
            "reasoning": "Too expensive", "objections": ["Price is too high"],
            "emotional_reaction": "doubtful", "would_pay": False,
        },
        "timeline": [],
        "discussions": [],
        "peer_warnings": [
            {"tick": 2, "source_name": "Bob", "theme": "price",
             "content": "Way too expensive for what it offers", "delta": -0.05},
        ],
    }
    system = format_ask_npc_system(ctx)

    assert "WHAT YOU'VE HEARD FROM OTHERS" in system
    assert "Bob" in system
    assert "price" in system
    assert "Way too expensive" in system


def test_ask_npc_no_peer_warnings():
    """When no peer warnings exist, shows placeholder text."""
    ctx = {
        "npc_profile": {
            "name": "Alice", "age": 30, "occupation": "Designer",
            "income_level": "middle", "communication_style": "direct",
            "personality": {}, "interests": [], "values": [], "pain_points": [],
        },
        "idea": {"title": "X", "description": "Y"},
        "current_state": {
            "stance": "aware", "interest_score": 0.5,
            "reasoning": "", "objections": [],
            "emotional_reaction": "", "would_pay": False,
        },
        "timeline": [],
        "discussions": [],
        "peer_warnings": [],
    }
    system = format_ask_npc_system(ctx)

    assert "No one has shared concerns" in system


# ---------------------------------------------------------------------------
# ConcernEvent source enrichment
# ---------------------------------------------------------------------------

def test_peer_warning_roundtrip():
    """PeerWarning data survives write -> read -> format cycle."""
    state = NpcState()
    state.aware = True
    state.interest_score = 0.5

    # Write a warning (simulating engine Phase 4b)
    warning = PeerWarning(
        tick=2, source_id="npc_alex", source_name="Alex",
        source_archetype="analytical_skeptic", theme="evidence",
        content="No peer-reviewed studies cited", delta=-0.04,
    )
    state.record_peer_warning(warning)

    # Read it back as if formatting for discussion
    result = format_social_memory(
        state.peer_warnings, state.discussion_memories, state.objection_themes,
    )
    assert "Alex" in result
    assert "evidence" in result
    assert "peer-reviewed" in result


def test_peer_warning_max_cap():
    """Only MAX_PEER_WARNINGS most recent warnings are kept."""
    state = NpcState()
    state.aware = True

    for i in range(10):
        state.record_peer_warning(PeerWarning(
            tick=i, source_id=f"npc_{i}", source_name=f"NPC{i}",
            source_archetype="x", theme="price",
            content=f"Concern {i}", delta=-0.01,
        ))

    assert len(state.peer_warnings) == 5  # MAX_PEER_WARNINGS
    # Most recent should be kept
    assert state.peer_warnings[-1].source_name == "NPC9"
    assert state.peer_warnings[0].source_name == "NPC5"
