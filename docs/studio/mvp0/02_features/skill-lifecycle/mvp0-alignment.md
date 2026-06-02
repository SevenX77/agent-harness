# skill-lifecycle — MVP0 Alignment (技能生命周期改造对齐方案)

This document establishes target specifications for conflict resolution whitelists, raw material uploads, and batch parameter configurators.

---

## 1. Re-aligned Feature Targets

### target 1: Resilience Against "Allow Overwrite" 403 Locking
* **Design Spec**: Add an automatic hash recovery and local merge mechanism:
  * When a user clicks `Allow Overwrite`, instead of immediately submitting with stale hashes:
    1. The client triggers a brief `GET` request fetching the server's current hash for that file.
    2. The local changes (appending whitelist targets) are merged dynamically into the retrieved content.
    3. The file write is re-submitted utilizing the fresh server-side hash, bypassing the 403 mismatch.
  * If conflict resolution fails, a clean visual dialog offers a "Force Overwrite" vs "Manually Revert" selection, preventing modal lockups.

---

### target 2: Interactive Source Materials Ingestion Manager
* **Design Spec**: Add a **Materials Ingestion Section** inside the Sidebar UI.
  * Users can upload raw non-JSON files (e.g. `.md` chapters or corpus `.txt`).
  * Supports bulk drag-and-drop operations.
  * Extracted files are indexed dynamically by the backend, eliminating the "501 Stub" test inputs limitations.

---

### target 3: Batch Run Regex File Pipeline Configurator
* **Design Spec**: Before executing a graph on a batch scale, an interactive configuration overlay allows users to specify:
  * **File Matching Selector**: Inputs files filtered by path expressions (e.g. `chapter_*.md`).
  * **Exclusion Filter**: Skip files matching specific strings (e.g. `*index*`, `*draft*`).
  * **Mapping Bindings**: Bind the matched file's name and raw text contents directly to graph properties:
    ```yaml
    batch_map:
      chapter_number: "regex_group_1"
      content: "file_body_content"
    ```
* **Rationale**: Bypasses the constraint requiring inputs to be pre-processed JSONs. Users can upload raw novels and configure batch filters purely from the visual editor.
