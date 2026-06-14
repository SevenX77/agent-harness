//! D12 / native-fs: the Rust sole-writer for local workspace files.
//!
//! All skill/graph/copilot writes route through these commands so a single
//! writer owns the local filesystem (the design forbids a Python+Rust dual
//! writer). Hashing is byte-compatible with the Python writer's
//! `_graph_content_hash` (SHA-256 hex of UTF-8) so the optimistic
//! expected-hash guard matches across writers, and the HashConflict error
//! shape matches what the frontend (`api/client.ts`) parses.

use std::path::{Component, Path, PathBuf};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

/// Workspace root id validator: mirrors Python `_SAFE_SKILL_ID_RE`
/// (`^[A-Za-z0-9][A-Za-z0-9._-]*$`) so a short id we accept here is also valid
/// in the backend. Plus the segment-equality guard (no path components).
fn is_valid_default_workspace_skill_id(raw: &str) -> bool {
    if raw.is_empty() || raw == "." || raw == ".." {
        return false;
    }
    if raw.contains('/') || raw.contains('\\') {
        return false;
    }
    let mut chars = raw.chars();
    let first = match chars.next() {
        Some(c) => c,
        None => return false,
    };
    if !(first.is_ascii_alphanumeric()) {
        return false;
    }
    for c in chars {
        if !(c.is_ascii_alphanumeric() || c == '.' || c == '_' || c == '-') {
            return false;
        }
    }
    true
}

/// Resolve a `workspace_root` arg from the frontend to a real absolute dir.
///
/// Two callers feed this:
/// - **Opened-folder workspace**: frontend passes the absolute workspace root
///   path (resolved via `resolveWorkspaceIdentity`). We return it as-is.
/// - **Default-workspace skill** (the user opened a skill from "Recent skills"
///   without a hosting folder): `resolveWorkspaceIdentity` cannot supply a
///   root, so the frontend falls back to the short skill id (e.g. `e2e-fast`).
///   We resolve it to `<config_dir>/workspaces/default/skills/<id>` — the same
///   layout Python `default_workspace_skills_dir()` uses — so native writes
///   land in the right place instead of failing to resolve.
///
/// Anything else (a relative path with slashes, an invalid id, or a short id
/// whose directory doesn't actually contain a skill body) is rejected with a
/// clear message so silent path-targeting bugs cannot regress.
pub fn resolve_workspace_root(raw: &str, config_dir: &Path) -> Result<PathBuf, String> {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return Err("workspace root is required".to_string());
    }
    let path = Path::new(trimmed);
    if path.is_absolute() {
        return Ok(path.to_path_buf());
    }
    if !is_valid_default_workspace_skill_id(trimmed) {
        return Err(format!(
            "workspace root must be an absolute path or a default-workspace skill id; got: {trimmed}"
        ));
    }
    let candidate = config_dir
        .join("workspaces")
        .join("default")
        .join("skills")
        .join(trimmed);
    if !candidate.join("GRAPH.md").is_file() {
        return Err(format!(
            "unknown default-workspace skill: {trimmed} (looked under {})",
            candidate.display()
        ));
    }
    Ok(candidate)
}

/// SHA-256 hex of UTF-8 content. Must stay byte-compatible with Python
/// `_graph_content_hash` (services/skills.py) so cross-writer hash conflicts
/// are detected identically.
pub fn sha256_hex(content: &str) -> String {
    let digest = Sha256::digest(content.as_bytes());
    let mut out = String::with_capacity(digest.len() * 2);
    for byte in digest {
        use std::fmt::Write as _;
        // Infallible for String writes; ignore the formatting Result.
        let _ = write!(out, "{byte:02x}");
    }
    out
}

/// Join a workspace-relative path onto `root`, rejecting absolute paths and any
/// parent (`..`) / root traversal so a write can never escape the workspace.
pub fn safe_join(root: &Path, rel: &str) -> Result<PathBuf, String> {
    let trimmed = rel.trim();
    if trimmed.is_empty() {
        return Err("path is required".to_string());
    }
    let rel_path = Path::new(trimmed);
    if rel_path.is_absolute() {
        return Err(format!("path must be workspace-relative: {trimmed}"));
    }
    let mut result = root.to_path_buf();
    for component in rel_path.components() {
        match component {
            Component::Normal(part) => result.push(part),
            Component::CurDir => {}
            Component::ParentDir | Component::RootDir | Component::Prefix(_) => {
                return Err(format!("invalid path segment in: {trimmed}"));
            }
        }
    }
    Ok(result)
}

#[derive(Serialize, Debug)]
pub struct WriteOutcome {
    pub path: String,
    pub hash: String,
}

/// Serializes to the exact error shape the frontend parses:
/// `{ "type": "HashConflict", "data": { current_hash, current_content } }`.
#[derive(Serialize, Debug)]
#[serde(tag = "type", content = "data")]
pub enum WriteWorkspaceError {
    HashConflict {
        current_hash: String,
        current_content: String,
    },
    WriteFailed {
        message: String,
    },
}

fn write_failed(message: String) -> WriteWorkspaceError {
    WriteWorkspaceError::WriteFailed { message }
}

/// Sole-writer file write (D12). Mirrors Python `update_skill_file`: optimistic
/// expected-hash guard, atomic temp+rename, returns the new content hash.
pub fn write_workspace_file_impl(
    workspace_root: &str,
    path: &str,
    content: &str,
    expected_hash: Option<&str>,
) -> Result<WriteOutcome, WriteWorkspaceError> {
    let root = PathBuf::from(workspace_root.trim());
    let target = safe_join(&root, path).map_err(write_failed)?;

    let current = match std::fs::read_to_string(&target) {
        Ok(text) => text,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => String::new(),
        Err(error) => return Err(write_failed(format!("cannot read current file: {error}"))),
    };
    let current_hash = sha256_hex(&current);
    if let Some(expected) = expected_hash {
        if current_hash != expected {
            return Err(WriteWorkspaceError::HashConflict {
                current_hash,
                current_content: current,
            });
        }
    }

    if let Some(parent) = target.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| write_failed(format!("cannot create parent dir: {error}")))?;
    }

    // Atomic publish: write a sibling temp file then rename over the target.
    let mut temp_os = target.clone().into_os_string();
    temp_os.push(".native-tmp");
    let temp = PathBuf::from(temp_os);
    std::fs::write(&temp, content)
        .map_err(|error| write_failed(format!("cannot write temp file: {error}")))?;
    std::fs::rename(&temp, &target)
        .map_err(|error| write_failed(format!("cannot finalize write: {error}")))?;

    Ok(WriteOutcome {
        path: path.to_string(),
        hash: sha256_hex(content),
    })
}

// ── Safe-write checkpoints (copilot F5, model B) ────────────────────────────
//
// Cursor-style apply-then-review: a copilot Write/Edit is applied immediately
// (so compile/predict/run use it), but the pre-edit bytes are checkpointed so a
// Reject can restore them exactly. The checkpoint is captured by Rust and the
// restore write goes back through the sole writer — the design requires "Reject
// 经 Rust 从 checkpoint 还原", and D12 keeps Rust as the only writer.
//
// At most one checkpoint per file: the FIRST unreviewed edit records the
// before-state; later edits before review do not overwrite it, so Reject always
// rewinds to before the whole pending change. Accept clears the checkpoint.

const CHECKPOINT_DIR: &str = ".gemini/copilot/checkpoints";

#[derive(Serialize, Deserialize, Debug)]
struct CheckpointRecord {
    path: String,
    /// Whether the file existed before the first unreviewed edit. A Reject of a
    /// brand-new file must delete it, not write empty bytes.
    existed: bool,
    content: String,
}

#[derive(Serialize, Debug)]
pub struct CheckpointOutcome {
    pub path: String,
    pub existed: bool,
    /// false when a checkpoint already existed (earliest pre-edit state kept).
    pub created: bool,
}

#[derive(Serialize, Debug)]
pub struct RestoreOutcome {
    pub path: String,
    /// Whether the file exists after restore (false = the pending file was new
    /// and has been removed).
    pub existed: bool,
    pub content: String,
}

/// Checkpoint record location: `<root>/.gemini/copilot/checkpoints/<sha(path)>.json`.
/// Keyed by the hash of the relative path so any path maps to a safe filename.
fn checkpoint_path(root: &Path, rel: &str) -> PathBuf {
    root.join(CHECKPOINT_DIR)
        .join(format!("{}.json", sha256_hex(rel)))
}

fn write_atomic(target: &Path, bytes: &str) -> Result<(), String> {
    if let Some(parent) = target.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("cannot create parent dir: {error}"))?;
    }
    let mut temp_os = target.to_path_buf().into_os_string();
    temp_os.push(".native-tmp");
    let temp = PathBuf::from(temp_os);
    std::fs::write(&temp, bytes).map_err(|error| format!("cannot write temp file: {error}"))?;
    std::fs::rename(&temp, target).map_err(|error| format!("cannot finalize write: {error}"))?;
    Ok(())
}

/// Capture the pre-edit state of `<root>/<path>` so it can be restored on
/// Reject. No-op (returns `created:false`) if a checkpoint already exists, so
/// the earliest before-state survives a run of edits.
pub fn checkpoint_workspace_file_impl(
    workspace_root: &str,
    path: &str,
) -> Result<CheckpointOutcome, String> {
    let root = PathBuf::from(workspace_root.trim());
    let target = safe_join(&root, path)?;
    let ckpt = checkpoint_path(&root, path.trim());

    if ckpt.is_file() {
        let existing = std::fs::read_to_string(&ckpt)
            .map_err(|error| format!("cannot read existing checkpoint: {error}"))?;
        let record: CheckpointRecord = serde_json::from_str(&existing)
            .map_err(|error| format!("corrupt checkpoint record: {error}"))?;
        return Ok(CheckpointOutcome {
            path: path.to_string(),
            existed: record.existed,
            created: false,
        });
    }

    let (existed, content) = match std::fs::read_to_string(&target) {
        Ok(text) => (true, text),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => (false, String::new()),
        Err(error) => return Err(format!("cannot read file to checkpoint: {error}")),
    };
    let record = CheckpointRecord {
        path: path.to_string(),
        existed,
        content,
    };
    let serialized = serde_json::to_string(&record)
        .map_err(|error| format!("cannot serialize checkpoint: {error}"))?;
    write_atomic(&ckpt, &serialized)?;
    Ok(CheckpointOutcome {
        path: path.to_string(),
        existed,
        created: true,
    })
}

/// Seed a checkpoint from EXPLICIT pre-edit state (no file re-read). Used by the
/// copilot safe-write flow: the backend captures before-bytes in its can_use_tool
/// callback and ships them in the patch_proposed event, so the frontend records
/// the checkpoint race-free (re-reading the file here would capture the already
/// applied edit). Earliest-wins, like `checkpoint_workspace_file_impl`.
pub fn seed_workspace_checkpoint_impl(
    workspace_root: &str,
    path: &str,
    content: &str,
    existed: bool,
) -> Result<CheckpointOutcome, String> {
    let root = PathBuf::from(workspace_root.trim());
    safe_join(&root, path)?;
    let ckpt = checkpoint_path(&root, path.trim());
    if ckpt.is_file() {
        return Ok(CheckpointOutcome {
            path: path.to_string(),
            existed,
            created: false,
        });
    }
    let record = CheckpointRecord {
        path: path.to_string(),
        existed,
        content: content.to_string(),
    };
    let serialized = serde_json::to_string(&record)
        .map_err(|error| format!("cannot serialize checkpoint: {error}"))?;
    write_atomic(&ckpt, &serialized)?;
    Ok(CheckpointOutcome {
        path: path.to_string(),
        existed,
        created: true,
    })
}

/// Restore `<root>/<path>` to its checkpointed pre-edit state and clear the
/// checkpoint. A file that did not exist before is removed. Errors if there is
/// no checkpoint — Reject without a captured before-state is a bug, not a no-op.
pub fn restore_workspace_file_impl(
    workspace_root: &str,
    path: &str,
) -> Result<RestoreOutcome, String> {
    let root = PathBuf::from(workspace_root.trim());
    let target = safe_join(&root, path)?;
    let ckpt = checkpoint_path(&root, path.trim());

    let serialized = std::fs::read_to_string(&ckpt).map_err(|error| {
        if error.kind() == std::io::ErrorKind::NotFound {
            format!("no checkpoint to restore for: {path}")
        } else {
            format!("cannot read checkpoint: {error}")
        }
    })?;
    let record: CheckpointRecord = serde_json::from_str(&serialized)
        .map_err(|error| format!("corrupt checkpoint record: {error}"))?;

    if record.existed {
        write_atomic(&target, &record.content)?;
    } else if target.exists() {
        std::fs::remove_file(&target)
            .map_err(|error| format!("cannot remove pending new file on restore: {error}"))?;
    }
    std::fs::remove_file(&ckpt)
        .map_err(|error| format!("restored but cannot clear checkpoint: {error}"))?;

    Ok(RestoreOutcome {
        path: path.to_string(),
        existed: record.existed,
        content: record.content,
    })
}

/// Discard the checkpoint for `<root>/<path>` (Accept keeps the applied edit).
/// Idempotent — a missing checkpoint is not an error.
pub fn clear_workspace_checkpoint_impl(workspace_root: &str, path: &str) -> Result<(), String> {
    let root = PathBuf::from(workspace_root.trim());
    safe_join(&root, path)?;
    let ckpt = checkpoint_path(&root, path.trim());
    match std::fs::remove_file(&ckpt) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(format!("cannot clear checkpoint: {error}")),
    }
}

/// Read outcome mirrors the writer (`WriteOutcome`): the caller gets both the
/// content and its content-addressable hash so it can pass the hash back as
/// `expected_hash` on a subsequent write without re-hashing the body.
#[derive(Serialize, Debug)]
pub struct ReadOutcome {
    pub path: String,
    pub content: String,
    pub hash: String,
}

/// Sole-reader counterpart to `write_workspace_file_impl`. Reads a file from
/// `<workspace_root>/<path>`, returning content + sha256-hex, refusing path
/// traversal so a read can never escape the workspace.
pub fn read_workspace_file_impl(workspace_root: &str, path: &str) -> Result<ReadOutcome, String> {
    let root = PathBuf::from(workspace_root.trim());
    let target = safe_join(&root, path)?;
    let content = std::fs::read_to_string(&target).map_err(|error| {
        if error.kind() == std::io::ErrorKind::NotFound {
            format!("file not found: {path}")
        } else {
            format!("cannot read file: {error}")
        }
    })?;
    Ok(ReadOutcome {
        path: path.to_string(),
        hash: sha256_hex(&content),
        content,
    })
}

/// One directory entry — `kind` is `"file"` or `"dir"` (symlinks fold into the
/// kind of their target so callers don't have to special-case them).
#[derive(Serialize, Debug, PartialEq)]
pub struct WorkspaceDirEntry {
    pub name: String,
    pub kind: String,
}

/// List entries directly under `<workspace_root>/<relative_dir>` (non-recursive).
/// A missing directory is surfaced as an empty list rather than an error so
/// callers can probe optional dirs (e.g. `.gemini/copilot/sessions/<skill>`)
/// without `if exists` ceremony — distinguishing "missing" from "empty" isn't
/// useful for the hydrate path that consumes this.
pub fn list_workspace_dir_impl(
    workspace_root: &str,
    relative_dir: &str,
) -> Result<Vec<WorkspaceDirEntry>, String> {
    let root = PathBuf::from(workspace_root.trim());
    let target = safe_join(&root, relative_dir)?;
    let read_dir = match std::fs::read_dir(&target) {
        Ok(iter) => iter,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(format!("cannot list directory: {error}")),
    };
    let mut entries = Vec::new();
    for entry in read_dir {
        let entry = entry.map_err(|error| format!("cannot read directory entry: {error}"))?;
        let name = entry.file_name().to_string_lossy().to_string();
        let metadata = entry
            .metadata()
            .map_err(|error| format!("cannot stat entry {name}: {error}"))?;
        let kind = if metadata.is_dir() {
            "dir"
        } else if metadata.is_file() {
            "file"
        } else {
            // Skip sockets/fifos/etc. — hydrate paths only care about regular
            // files and directories.
            continue;
        };
        entries.push(WorkspaceDirEntry {
            name,
            kind: kind.to_string(),
        });
    }
    // Deterministic order so callers (and tests) don't rely on filesystem
    // iteration order which varies by platform.
    entries.sort_by(|a, b| a.name.cmp(&b.name));
    Ok(entries)
}

#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
pub struct RecentWorkspace {
    pub absolute_path: String,
    pub display_name: String,
    pub identity: String,
    pub last_opened_at: String,
}

/// Upsert by identity, most-recent first (dedupes prior entries for the same
/// workspace).
pub fn upsert_recent(
    mut list: Vec<RecentWorkspace>,
    entry: RecentWorkspace,
) -> Vec<RecentWorkspace> {
    list.retain(|item| item.identity != entry.identity);
    list.insert(0, entry);
    list
}

pub fn remove_recent(mut list: Vec<RecentWorkspace>, identity: &str) -> Vec<RecentWorkspace> {
    list.retain(|item| item.identity != identity);
    list
}

fn read_recent(path: &Path) -> Vec<RecentWorkspace> {
    let raw = match std::fs::read_to_string(path) {
        Ok(raw) => raw,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Vec::new(),
        Err(error) => {
            log::warn!(
                "native_fs.read_recent: cannot read {}: {error}",
                path.display()
            );
            return Vec::new();
        }
    };
    match serde_json::from_str(&raw) {
        Ok(list) => list,
        Err(error) => {
            log::warn!(
                "native_fs.read_recent: corrupt recent-workspaces file {}, resetting: {error}",
                path.display()
            );
            Vec::new()
        }
    }
}

fn write_recent(path: &Path, list: &[RecentWorkspace]) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("cannot create config dir: {error}"))?;
    }
    let raw = serde_json::to_string_pretty(list)
        .map_err(|error| format!("cannot serialize recent workspaces: {error}"))?;
    std::fs::write(path, raw).map_err(|error| format!("cannot write recent workspaces: {error}"))
}

fn recent_workspaces_file() -> PathBuf {
    crate::sidecar::default_user_config_dir().join("recent_workspaces.json")
}

#[tauri::command]
pub fn write_workspace_file(
    workspace_root: String,
    path: String,
    content: String,
    expected_hash: Option<String>,
) -> Result<WriteOutcome, WriteWorkspaceError> {
    let config_dir = crate::resolve_config_dir();
    let resolved = resolve_workspace_root(&workspace_root, &config_dir).map_err(write_failed)?;
    write_workspace_file_impl(
        &resolved.to_string_lossy(),
        &path,
        &content,
        expected_hash.as_deref(),
    )
}

#[tauri::command]
pub fn add_recent_workspace(
    absolute_path: String,
    display_name: String,
    identity: String,
    last_opened_at: String,
) -> Result<(), String> {
    let file = recent_workspaces_file();
    let updated = upsert_recent(
        read_recent(&file),
        RecentWorkspace {
            absolute_path,
            display_name,
            identity,
            last_opened_at,
        },
    );
    write_recent(&file, &updated)
}

#[tauri::command]
pub fn list_recent_workspaces() -> Vec<RecentWorkspace> {
    read_recent(&recent_workspaces_file())
}

#[tauri::command]
pub fn remove_recent_workspace(identity: String) -> Result<(), String> {
    let file = recent_workspaces_file();
    let updated = remove_recent(read_recent(&file), &identity);
    write_recent(&file, &updated)
}

#[tauri::command]
pub fn read_workspace_file(workspace_root: String, path: String) -> Result<ReadOutcome, String> {
    let config_dir = crate::resolve_config_dir();
    let resolved = resolve_workspace_root(&workspace_root, &config_dir)?;
    read_workspace_file_impl(&resolved.to_string_lossy(), &path)
}

#[tauri::command]
pub fn list_workspace_dir(
    workspace_root: String,
    relative_dir: String,
) -> Result<Vec<WorkspaceDirEntry>, String> {
    let config_dir = crate::resolve_config_dir();
    let resolved = resolve_workspace_root(&workspace_root, &config_dir)?;
    list_workspace_dir_impl(&resolved.to_string_lossy(), &relative_dir)
}

#[tauri::command]
pub fn checkpoint_workspace_file(
    workspace_root: String,
    path: String,
) -> Result<CheckpointOutcome, String> {
    let config_dir = crate::resolve_config_dir();
    let resolved = resolve_workspace_root(&workspace_root, &config_dir)?;
    checkpoint_workspace_file_impl(&resolved.to_string_lossy(), &path)
}

#[tauri::command]
pub fn seed_workspace_checkpoint(
    workspace_root: String,
    path: String,
    content: String,
    existed: bool,
) -> Result<CheckpointOutcome, String> {
    let config_dir = crate::resolve_config_dir();
    let resolved = resolve_workspace_root(&workspace_root, &config_dir)?;
    seed_workspace_checkpoint_impl(&resolved.to_string_lossy(), &path, &content, existed)
}

#[tauri::command]
pub fn restore_workspace_file(
    workspace_root: String,
    path: String,
) -> Result<RestoreOutcome, String> {
    let config_dir = crate::resolve_config_dir();
    let resolved = resolve_workspace_root(&workspace_root, &config_dir)?;
    restore_workspace_file_impl(&resolved.to_string_lossy(), &path)
}

#[tauri::command]
pub fn clear_workspace_checkpoint(workspace_root: String, path: String) -> Result<(), String> {
    let config_dir = crate::resolve_config_dir();
    let resolved = resolve_workspace_root(&workspace_root, &config_dir)?;
    clear_workspace_checkpoint_impl(&resolved.to_string_lossy(), &path)
}

#[tauri::command]
pub fn ensure_workspace_support_dirs(workspace_root: String) -> Result<(), String> {
    let config_dir = crate::resolve_config_dir();
    let root = resolve_workspace_root(&workspace_root, &config_dir)?;
    let sessions = root.join(".gemini").join("copilot").join("sessions");
    std::fs::create_dir_all(&sessions)
        .map_err(|error| format!("cannot create support dirs: {error}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_root(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "skill-studio-native-fs-{name}-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).expect("temp root");
        dir
    }

    #[test]
    fn sha256_hex_matches_python_known_vectors() {
        // Same algorithm as Python hashlib.sha256(x.encode()).hexdigest().
        assert_eq!(
            sha256_hex(""),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
        assert_eq!(
            sha256_hex("hello"),
            "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        );
    }

    #[test]
    fn safe_join_rejects_traversal_and_absolute() {
        let root = Path::new("/tmp/ws");
        assert!(safe_join(root, "../escape.md").is_err());
        assert!(safe_join(root, "/etc/passwd").is_err());
        assert!(safe_join(root, "  ").is_err());
        assert_eq!(
            safe_join(root, "phases/setup/LOGIC.md").unwrap(),
            PathBuf::from("/tmp/ws/phases/setup/LOGIC.md")
        );
    }

    #[test]
    fn write_creates_file_and_returns_content_hash() {
        let root = temp_root("write-new");
        let outcome =
            write_workspace_file_impl(root.to_str().unwrap(), "GRAPH.md", "graph body", None)
                .expect("write");
        assert_eq!(outcome.hash, sha256_hex("graph body"));
        assert_eq!(
            std::fs::read_to_string(root.join("GRAPH.md")).unwrap(),
            "graph body"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn write_with_matching_expected_hash_succeeds() {
        let root = temp_root("write-match");
        write_workspace_file_impl(root.to_str().unwrap(), "a.md", "one", None).unwrap();
        let outcome = write_workspace_file_impl(
            root.to_str().unwrap(),
            "a.md",
            "two",
            Some(&sha256_hex("one")),
        )
        .expect("write with matching expected hash");
        assert_eq!(outcome.hash, sha256_hex("two"));
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn write_with_stale_expected_hash_reports_conflict_with_current() {
        let root = temp_root("write-conflict");
        write_workspace_file_impl(root.to_str().unwrap(), "a.md", "current", None).unwrap();
        let error =
            write_workspace_file_impl(root.to_str().unwrap(), "a.md", "incoming", Some("deadbeef"))
                .expect_err("stale expected hash");
        match error {
            WriteWorkspaceError::HashConflict {
                current_hash,
                current_content,
            } => {
                assert_eq!(current_content, "current");
                assert_eq!(current_hash, sha256_hex("current"));
            }
            WriteWorkspaceError::WriteFailed { message } => panic!("unexpected: {message}"),
        }
        // The on-disk file must be untouched on conflict.
        assert_eq!(
            std::fs::read_to_string(root.join("a.md")).unwrap(),
            "current"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn hash_conflict_serializes_to_frontend_shape() {
        let error = WriteWorkspaceError::HashConflict {
            current_hash: "abc".to_string(),
            current_content: "body".to_string(),
        };
        let value = serde_json::to_value(&error).unwrap();
        assert_eq!(value["type"], "HashConflict");
        assert_eq!(value["data"]["current_hash"], "abc");
        assert_eq!(value["data"]["current_content"], "body");
    }

    #[test]
    fn recent_workspaces_upsert_dedupes_and_orders_most_recent_first() {
        let a = RecentWorkspace {
            absolute_path: "/ws/a".to_string(),
            display_name: "A".to_string(),
            identity: "id-a".to_string(),
            last_opened_at: "t1".to_string(),
        };
        let b = RecentWorkspace {
            absolute_path: "/ws/b".to_string(),
            display_name: "B".to_string(),
            identity: "id-b".to_string(),
            last_opened_at: "t2".to_string(),
        };
        let a_again = RecentWorkspace {
            last_opened_at: "t3".to_string(),
            ..a.clone()
        };
        let list = upsert_recent(upsert_recent(vec![], a), b.clone());
        let list = upsert_recent(list, a_again.clone());
        assert_eq!(list, vec![a_again, b]);
    }

    #[test]
    fn recent_workspaces_roundtrip_through_disk() {
        let root = temp_root("recent");
        let file = root.join("recent_workspaces.json");
        let entry = RecentWorkspace {
            absolute_path: "/ws/x".to_string(),
            display_name: "X".to_string(),
            identity: "id-x".to_string(),
            last_opened_at: "t".to_string(),
        };
        write_recent(&file, &upsert_recent(read_recent(&file), entry.clone())).unwrap();
        assert_eq!(read_recent(&file), vec![entry.clone()]);
        let pruned = remove_recent(read_recent(&file), "id-x");
        write_recent(&file, &pruned).unwrap();
        assert!(read_recent(&file).is_empty());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn ensure_support_dirs_creates_copilot_sessions() {
        let root = temp_root("support");
        ensure_workspace_support_dirs(root.to_str().unwrap().to_string()).unwrap();
        assert!(root
            .join(".gemini")
            .join("copilot")
            .join("sessions")
            .is_dir());
        let _ = std::fs::remove_dir_all(&root);
    }

    /// Seed a fake default-workspace `<config_dir>/workspaces/default/skills/<id>/GRAPH.md`
    /// so `resolve_workspace_root` accepts the short id. Mirrors the on-disk layout
    /// the Python backend (`default_workspace_skills_dir()`) writes for default-user
    /// skills opened from "Recent skills".
    fn seed_default_workspace_skill(config_dir: &Path, skill_id: &str) {
        let dir = config_dir
            .join("workspaces")
            .join("default")
            .join("skills")
            .join(skill_id);
        std::fs::create_dir_all(&dir).expect("seed skill dir");
        std::fs::write(dir.join("GRAPH.md"), "schema_version: \"v0.3.0\"\n")
            .expect("seed GRAPH.md");
    }

    #[test]
    fn resolve_workspace_root_passes_absolute_path_through() {
        let abs = temp_root("resolve-abs");
        // Config dir is irrelevant when an absolute path is supplied.
        let resolved =
            resolve_workspace_root(abs.to_str().unwrap(), Path::new("/nonexistent-config"))
                .expect("absolute path resolves unchanged");
        assert_eq!(resolved, abs);
        let _ = std::fs::remove_dir_all(&abs);
    }

    #[test]
    fn resolve_workspace_root_resolves_default_workspace_short_id() {
        let config = temp_root("resolve-shortid");
        seed_default_workspace_skill(&config, "e2e-fast");
        let resolved = resolve_workspace_root("e2e-fast", &config)
            .expect("short id resolves under default workspace");
        assert_eq!(
            resolved,
            config
                .join("workspaces")
                .join("default")
                .join("skills")
                .join("e2e-fast")
        );
        let _ = std::fs::remove_dir_all(&config);
    }

    #[test]
    fn resolve_workspace_root_rejects_short_id_without_graph_body() {
        let config = temp_root("resolve-noskill");
        // No seeded skill: the directory does not exist, so the resolver must refuse
        // rather than silently create a phantom skill dir on first write.
        let error =
            resolve_workspace_root("ghost-skill", &config).expect_err("missing skill is rejected");
        assert!(
            error.contains("unknown default-workspace skill"),
            "unexpected error: {error}"
        );
        let _ = std::fs::remove_dir_all(&config);
    }

    #[test]
    fn resolve_workspace_root_rejects_invalid_ids_and_traversal() {
        let config = temp_root("resolve-bad");
        // Path components / traversal must be refused even before disk lookup so the
        // resolver cannot be tricked into escaping the default-workspace tree.
        for bad in [
            "",
            "  ",
            ".",
            "..",
            "../escape",
            "a/b",
            "a\\b",
            "-leading-dash",
        ] {
            assert!(
                resolve_workspace_root(bad, &config).is_err(),
                "expected rejection for {bad:?}"
            );
        }
        let _ = std::fs::remove_dir_all(&config);
    }

    #[test]
    fn read_workspace_file_returns_content_and_matching_hash() {
        let root = temp_root("read-basic");
        std::fs::write(root.join("note.md"), "hello world").unwrap();
        let outcome =
            read_workspace_file_impl(root.to_str().unwrap(), "note.md").expect("read existing");
        assert_eq!(outcome.path, "note.md");
        assert_eq!(outcome.content, "hello world");
        // The reader's hash must match what the writer's `WriteOutcome.hash`
        // would have produced for the same bytes, so callers can feed it
        // straight into `expected_hash` for a follow-up write without
        // re-hashing.
        assert_eq!(outcome.hash, sha256_hex("hello world"));
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn read_workspace_file_clearly_reports_missing() {
        let root = temp_root("read-missing");
        let error = read_workspace_file_impl(root.to_str().unwrap(), "nope.json")
            .expect_err("missing file rejected");
        assert!(error.contains("file not found"), "unexpected: {error}");
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn read_workspace_file_refuses_traversal() {
        let root = temp_root("read-traversal");
        // Reads must not escape the workspace — the writer's safe_join also
        // refuses these, and the reader inherits that guard. Without it a
        // request for `../../etc/passwd` could leak host files.
        assert!(read_workspace_file_impl(root.to_str().unwrap(), "../escape.md").is_err());
        assert!(read_workspace_file_impl(root.to_str().unwrap(), "/etc/passwd").is_err());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn list_workspace_dir_returns_sorted_files_and_dirs() {
        let root = temp_root("list-basic");
        std::fs::create_dir_all(root.join("sub")).unwrap();
        std::fs::write(root.join("b.json"), "{}").unwrap();
        std::fs::write(root.join("a.json"), "{}").unwrap();
        let entries =
            list_workspace_dir_impl(root.to_str().unwrap(), ".").expect("list workspace root");
        // Sort guarantees deterministic order for callers and tests; the
        // platform-native iteration order is not stable.
        assert_eq!(
            entries,
            vec![
                WorkspaceDirEntry {
                    name: "a.json".to_string(),
                    kind: "file".to_string()
                },
                WorkspaceDirEntry {
                    name: "b.json".to_string(),
                    kind: "file".to_string()
                },
                WorkspaceDirEntry {
                    name: "sub".to_string(),
                    kind: "dir".to_string()
                },
            ]
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn list_workspace_dir_treats_missing_dir_as_empty() {
        let root = temp_root("list-missing");
        // Optional dirs (e.g. `.gemini/copilot/sessions/<skill>` on first
        // launch) should produce an empty list, not an error — callers can
        // hydrate without a pre-flight `exists()` check.
        let entries = list_workspace_dir_impl(root.to_str().unwrap(), ".gemini/copilot/sessions")
            .expect("missing dir maps to empty list");
        assert!(entries.is_empty());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn list_workspace_dir_refuses_traversal() {
        let root = temp_root("list-traversal");
        assert!(list_workspace_dir_impl(root.to_str().unwrap(), "../escape").is_err());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn checkpoint_then_restore_rewinds_an_edited_file_to_original_bytes() {
        let root = temp_root("ckpt-edit");
        let rs = root.to_str().unwrap();
        std::fs::write(root.join("GRAPH.md"), "original").unwrap();

        // Capture before-state, then a copilot edit lands on disk.
        let cp = checkpoint_workspace_file_impl(rs, "GRAPH.md").expect("checkpoint");
        assert!(cp.created && cp.existed);
        write_workspace_file_impl(rs, "GRAPH.md", "edited by copilot", None).unwrap();
        assert_eq!(
            std::fs::read_to_string(root.join("GRAPH.md")).unwrap(),
            "edited by copilot"
        );

        // Reject: Rust restores the original bytes and clears the checkpoint.
        let restored = restore_workspace_file_impl(rs, "GRAPH.md").expect("restore");
        assert_eq!(restored.content, "original");
        assert!(restored.existed);
        assert_eq!(
            std::fs::read_to_string(root.join("GRAPH.md")).unwrap(),
            "original"
        );
        // Checkpoint consumed — a second restore has nothing to do.
        assert!(restore_workspace_file_impl(rs, "GRAPH.md").is_err());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn restore_removes_a_file_that_did_not_exist_before_the_edit() {
        let root = temp_root("ckpt-new");
        let rs = root.to_str().unwrap();
        // No file yet → checkpoint records existed:false.
        let cp = checkpoint_workspace_file_impl(rs, "new.md").expect("checkpoint");
        assert!(cp.created && !cp.existed);
        write_workspace_file_impl(rs, "new.md", "fresh content", None).unwrap();
        assert!(root.join("new.md").is_file());

        let restored = restore_workspace_file_impl(rs, "new.md").expect("restore");
        assert!(!restored.existed);
        // Reject of a brand-new file deletes it rather than leaving empty bytes.
        assert!(!root.join("new.md").exists());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn second_checkpoint_keeps_earliest_before_state() {
        let root = temp_root("ckpt-earliest");
        let rs = root.to_str().unwrap();
        std::fs::write(root.join("g.md"), "v0").unwrap();

        let first = checkpoint_workspace_file_impl(rs, "g.md").expect("first checkpoint");
        assert!(first.created);
        write_workspace_file_impl(rs, "g.md", "v1", None).unwrap();
        // A second edit checkpoints again, but must NOT overwrite the v0 capture.
        let second = checkpoint_workspace_file_impl(rs, "g.md").expect("second checkpoint");
        assert!(!second.created);
        write_workspace_file_impl(rs, "g.md", "v2", None).unwrap();

        // Reject rewinds all the way to v0, not v1.
        let restored = restore_workspace_file_impl(rs, "g.md").expect("restore");
        assert_eq!(restored.content, "v0");
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn clear_checkpoint_keeps_the_applied_edit_and_is_idempotent() {
        let root = temp_root("ckpt-clear");
        let rs = root.to_str().unwrap();
        std::fs::write(root.join("g.md"), "before").unwrap();
        checkpoint_workspace_file_impl(rs, "g.md").unwrap();
        write_workspace_file_impl(rs, "g.md", "after-accept", None).unwrap();

        // Accept: clear the checkpoint, applied edit stays.
        clear_workspace_checkpoint_impl(rs, "g.md").expect("clear");
        assert_eq!(
            std::fs::read_to_string(root.join("g.md")).unwrap(),
            "after-accept"
        );
        // Idempotent — clearing again is fine; restore now has nothing.
        clear_workspace_checkpoint_impl(rs, "g.md").expect("clear idempotent");
        assert!(restore_workspace_file_impl(rs, "g.md").is_err());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn seed_checkpoint_from_explicit_state_then_restore() {
        // Copilot safe-write path: backend captured before-bytes and shipped them
        // in the event; frontend seeds the checkpoint race-free (no file re-read).
        let root = temp_root("ckpt-seed");
        let rs = root.to_str().unwrap();
        // The file already holds the APPLIED edit (SDK wrote it); seed records the
        // before-state from explicit content, not by reading the edited file.
        std::fs::write(root.join("GRAPH.md"), "AFTER edit").unwrap();
        let cp = seed_workspace_checkpoint_impl(rs, "GRAPH.md", "BEFORE edit", true).expect("seed");
        assert!(cp.created && cp.existed);
        // Seeding again is earliest-wins (no overwrite).
        let again = seed_workspace_checkpoint_impl(rs, "GRAPH.md", "OTHER", true).expect("seed2");
        assert!(!again.created);

        let restored = restore_workspace_file_impl(rs, "GRAPH.md").expect("restore");
        assert_eq!(restored.content, "BEFORE edit");
        assert_eq!(
            std::fs::read_to_string(root.join("GRAPH.md")).unwrap(),
            "BEFORE edit"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn seed_checkpoint_for_new_file_restores_to_absent() {
        let root = temp_root("ckpt-seed-new");
        let rs = root.to_str().unwrap();
        std::fs::write(root.join("new.md"), "copilot wrote this").unwrap();
        // existed:false → Reject must delete the file the copilot created.
        seed_workspace_checkpoint_impl(rs, "new.md", "", false).expect("seed new");
        let restored = restore_workspace_file_impl(rs, "new.md").expect("restore");
        assert!(!restored.existed);
        assert!(!root.join("new.md").exists());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn checkpoint_and_restore_refuse_traversal() {
        let root = temp_root("ckpt-traversal");
        let rs = root.to_str().unwrap();
        assert!(checkpoint_workspace_file_impl(rs, "../escape.md").is_err());
        assert!(restore_workspace_file_impl(rs, "/etc/passwd").is_err());
        assert!(clear_workspace_checkpoint_impl(rs, "../escape.md").is_err());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn write_to_default_workspace_short_id_lands_under_config_dir_skills() {
        // End-to-end of the F2 default-workspace save path: the command receives
        // a short skill id (because resolveWorkspaceIdentity has no workspaceRoot
        // for default-workspace skills), the resolver maps it under
        // `<config_dir>/workspaces/default/skills/<id>`, and the writer puts the
        // file there. This is the bug the previous turn registered (writes
        // failed because the short id was used as a literal workspace root).
        let config = temp_root("write-shortid");
        seed_default_workspace_skill(&config, "e2e-fast");
        let skill_dir = config
            .join("workspaces")
            .join("default")
            .join("skills")
            .join("e2e-fast");

        let resolved =
            resolve_workspace_root("e2e-fast", &config).expect("resolver accepts short id");
        let outcome = write_workspace_file_impl(
            &resolved.to_string_lossy(),
            "GRAPH.md",
            "schema_version: \"v0.3.0\"\nname: e2e-fast\n",
            Some(&sha256_hex("schema_version: \"v0.3.0\"\n")),
        )
        .expect("write to default-workspace short id");
        assert_eq!(outcome.path, "GRAPH.md");
        assert_eq!(
            std::fs::read_to_string(skill_dir.join("GRAPH.md")).unwrap(),
            "schema_version: \"v0.3.0\"\nname: e2e-fast\n"
        );
        let _ = std::fs::remove_dir_all(&config);
    }

    #[test]
    fn resolve_workspace_root_trims_whitespace() {
        let abs = temp_root("resolve-trim");
        let raw = format!("  {}  ", abs.display());
        let resolved =
            resolve_workspace_root(&raw, Path::new("/nonexistent-config")).expect("trimmed path");
        assert_eq!(resolved, abs);
        let _ = std::fs::remove_dir_all(&abs);
    }
}
