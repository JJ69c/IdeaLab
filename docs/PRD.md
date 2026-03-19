# IdeaLab — Product Requirements Document

## Overview

IdeaLab is a synthetic population idea-testing engine. Users inject a product, idea,
or concept into a simulated society of AI-driven NPCs. The system runs a multi-round
social simulation and produces structured insight reports about adoption likelihood,
objections, viral potential, and user segment analysis.

## Problem Statement

Founders and product managers need early signal on whether an idea resonates before
investing weeks in development or thousands in user research. Current options are:
- Expensive and slow (formal user research)
- Biased and narrow (asking friends)
- Surface-level (social media polls)

IdeaLab provides a fast, cheap, repeatable "first pass" signal from a diverse
simulated population.

## Target User

Solo founders, product managers, indie hackers, and innovation teams who want fast
directional signal before committing resources.

## Core Use Case

1. User describes a product, idea, or concept in natural language
2. User selects a population template (or uses default)
3. System runs 5-10 rounds of social simulation
4. System outputs a structured report with:
   - Overall adoption score
   - Interest breakdown by persona segment
   - Key objections and concerns
   - Social spread dynamics
   - Actionable recommendations

## MVP Scope

### In Scope
- 20-50 pre-defined NPC personas with diverse profiles
- Persona attributes: demographics, personality traits, interests, pain points
- Social graph with trust-weighted connections
- Discrete tick-based simulation (5-10 rounds)
- Idea injection via web form
- LLM-driven NPC reactions and discussions
- Deterministic social influence and propagation math
- Structured JSON/dashboard report
- Simulation history persistence (SQLite)

### Out of Scope (v1)
- 3D world or visual map
- Real-time streaming simulation
- Voice interaction
- Custom NPC creation (Phase 3)
- Multi-user / team features
- Comparison mode (A/B idea testing)
- PDF export
- Mobile app

## Success Metrics (Internal)
- Can run a full simulation in under 3 minutes
- Cost per simulation under $0.15
- Report feels qualitatively useful (subjective, founder judgment)
- At least 3 distinct persona segments visible in output

## Key Risks
- LLM responses may be generic or repetitive across NPCs
- Simulation may feel "fake" if NPC reactions lack specificity
- Cost could scale unexpectedly with larger populations
- Users may over-trust synthetic results as real market validation

## Non-Functional Requirements
- Simulation must complete in under 5 minutes for 50 NPCs / 10 ticks
- API response times under 200ms for non-simulation endpoints
- System must work offline-capable (except LLM calls)
- Data must persist across sessions
