---
name: agent-prompt-design
description: Design and optimize prompts for LLM agent nodes, ensuring outputs strictly conform to output schemas and pass golden evaluations.
---

# Skill: Agent Node Prompt Design

This skill defines the methodology for drafting, structuring, and iterating prompts for LLM agent nodes.

## 1. Prompt as a Data Pipeline Transformation
An agent prompt is not a conversational instruction; it is a structured transformation within a data pipeline. Inputs consist of upstream outputs, and outputs must strictly match the phase's output JSON schema (`[[KB-04-agent-nodes]]`).

## 2. Five-Section Structure Template
Draft agent prompts using the following strict layout:
1.  **Role & Task**: Define the agent's identity and core transformation task in a single sentence (e.g., *"You are an editor, transform input A into format B"*). Avoid long narrative backstories.
2.  **Input Description**: Define the exact variables passed from the blackboard, explaining what is a variable, what is static context, and what controls decision logic.
3.  **Task Decomposition & Step Instructions**: Outline the sequential steps the model must follow to process the input. State explicit rules and conditions rather than leaving them open-ended.
4.  **Output Format Specification**: Declare the expected schema fields, types, and nesting, and provide a **complete, concrete JSON output example**.
5.  **Constraints & Fallback Paths**: Specify how to output errors or handle missing info (e.g., return specific null values or empty lists) to prevent the model from hallucinating.

## 3. Golden Alignment
*   Design the prompt so its outputs are easy to evaluate. Prefer structured/enumerated outputs over free-text fields (`[[KB-10-golden]]`).
*   Handle model temperature fluctuations by using structured fields to restrict variance.

## 4. Iteration Loop
*   Use actual blackboard input payloads to test predictions (`[[KB-08-predict]]`).
*   Modify only one prompt instruction or output key at a time, testing the impact before making further changes.
*   Capture failed cases and encode their corrections directly into the prompt's instructions or as negative examples.

## 5. Anti-Patterns
*   ❌ Relying on generic instructions like *"Please return JSON"* without specifying fields, types, or examples.
*   ❌ Copying and pasting upstream payloads into the prompt (use input references; the engine injects variables automatically).
*   ❌ Using polite or conversational language that does not impact model output behavior.
