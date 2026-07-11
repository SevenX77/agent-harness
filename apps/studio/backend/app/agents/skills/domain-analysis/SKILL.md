---
name: domain-analysis
description: Analyze unstructured domain documents and structure them into a formal domain framework (entities, workflows, rules, glossaries, and open questions) before starting graph design.
---

# Skill: Domain Analysis

This skill defines the methodology for decomposing unstructured domain materials into structured inputs suitable for graph skill creation.

## 1. Methodology Workflow

1.  **Thorough Investigation**: Read all input documents, files, and user messages completely before formulating any design. Never start designing based on incomplete context.
2.  **Structural Framework Extraction**: Categorize the analyzed information into the following five sections:
    *   **Entities**: Identify domain-specific nouns, concepts, and their properties (fields/attributes).
    *   **Workflows**: Model step-by-step sequences, conditional branches, and decision trees.
    *   **Rules**: Define constraints, validation requirements, boundaries, and logical prerequisites.
    *   **Glossary**: Map domain terminology and jargon to precise technical definitions.
    *   **Unresolved Questions**: Note gaps or contradictions in the materials. Explicitly ask the user to clarify these points rather than speculating.
3.  **Mapping to Graph Design**: Determine which parts of the workflow should be handled by deterministic code (LOGIC phases) and which require natural language processing (Agent phases). Suggest initial root inputs and outputs for the graph design phase.

## 2. Leveraging External Analysis

If analyzing complex domains, seek external viewpoints to detect blind spots:
1.  **Antigravity CLI**: If the CLI (`agy`) is available, run `agy --print "<question>"` via approved terminal commands to query external models (Gemini), then cross-verify results.
2.  **Gemini Roles**: If `agy` is unavailable but Gemini roles are configured, guide the user to test the prompt against alternative model routes.
3.  **Fallback**: If no external tools are configured, complete the analysis locally and explicitly state: *"This analysis was conducted without external analyzers."*

## 3. Anti-Patterns
*   ❌ Writing long-form prose summaries instead of the structured 5-section framework.
*   ❌ Commencing analysis before reading all user-provided files and context.
*   ❌ Inventing domain parameters or filling document gaps with personal assumptions.
