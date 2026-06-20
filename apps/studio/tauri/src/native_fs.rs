//! D12 / native-fs: the Rust sole-writer for local workspace files.
//!
//! All skill/graph/copilot writes route through these commands so a single
//! writer owns the local filesystem (the design forbids a Python+Rust dual
//! writer). Hashing is byte-compatible with the Python writer's
//! `_graph_content_hash` (SHA-256 hex of UTF-8) so the optimistic
//! expected-hash guard matches across writers, and the HashConflict error
//! shape matches what the frontend (`api/client.ts`) parses.

use std::io::Write as _;
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
/// parent (`..`) / root traversal. This is a lexical guard; callers that touch
/// disk must also verify existing symlinks resolve inside the workspace.
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

fn canonical_workspace_root(root: &Path) -> Result<PathBuf, String> {
    root.canonicalize()
        .map_err(|error| format!("cannot resolve workspace root: {error}"))
}

fn ensure_existing_path_components_inside_workspace(root: &Path, rel: &str) -> Result<(), String> {
    let canonical_root = canonical_workspace_root(root)?;
    let mut current = root.to_path_buf();
    for component in Path::new(rel.trim()).components() {
        match component {
            Component::Normal(part) => current.push(part),
            Component::CurDir => continue,
            Component::ParentDir | Component::RootDir | Component::Prefix(_) => {
                return Err(format!("invalid path segment in: {}", rel.trim()));
            }
        }

        match std::fs::symlink_metadata(&current) {
            Ok(_) => {
                let resolved = current.canonicalize().map_err(|error| {
                    format!(
                        "cannot resolve workspace path {}: {error}",
                        current.display()
                    )
                })?;
                if !resolved.starts_with(&canonical_root) {
                    return Err(format!("path escapes workspace: {}", current.display()));
                }
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
            Err(error) => {
                return Err(format!(
                    "cannot inspect workspace path {}: {error}",
                    current.display()
                ));
            }
        }
    }
    Ok(())
}

#[derive(Serialize, Debug)]
pub struct WriteOutcome {
    pub path: String,
    pub hash: String,
}

#[derive(Clone, Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct PublishPackageWriteRequest {
    pub release_version: String,
    pub content_hash: String,
    pub manifest_ref: String,
    pub artifact_ref: serde_json::Value,
}

#[derive(Serialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct PublishPackageWriteOutcome {
    pub path: String,
    pub native_path: String,
    pub hash: String,
    pub bytes_written: u64,
}

#[derive(Serialize, Debug)]
#[serde(tag = "type", content = "data")]
pub enum PublishPackageWriteError {
    PathEscape { message: String, path: String },
    Conflict { message: String, path: String },
    PermissionDenied { message: String, path: String },
    IoFailed { message: String, path: String },
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

fn package_path_escape(path: &str, message: String) -> PublishPackageWriteError {
    PublishPackageWriteError::PathEscape {
        message,
        path: path.to_string(),
    }
}

fn package_io_error(path: &str, prefix: &str, error: std::io::Error) -> PublishPackageWriteError {
    let message = format!("{prefix}: {error}");
    match error.kind() {
        std::io::ErrorKind::AlreadyExists => PublishPackageWriteError::Conflict {
            message,
            path: path.to_string(),
        },
        std::io::ErrorKind::PermissionDenied => PublishPackageWriteError::PermissionDenied {
            message,
            path: path.to_string(),
        },
        _ => PublishPackageWriteError::IoFailed {
            message,
            path: path.to_string(),
        },
    }
}

fn ensure_final_parent_inside_workspace(root: &Path, rel: &str) -> Result<(), String> {
    let target = safe_join(root, rel)?;
    let parent = target
        .parent()
        .ok_or_else(|| format!("path has no parent: {}", rel.trim()))?;
    let canonical_root = canonical_workspace_root(root)?;
    let resolved_parent = parent.canonicalize().map_err(|error| {
        format!(
            "cannot resolve workspace parent {}: {error}",
            parent.display()
        )
    })?;
    if !resolved_parent.starts_with(&canonical_root) {
        return Err(format!("path escapes workspace: {}", parent.display()));
    }
    Ok(())
}

/// Sole-writer file write (D12). Mirrors Python `update_skill_file`: optimistic
/// expected-hash guard, atomic temp+rename, returns the new content hash.
pub fn write_workspace_file_impl(
    workspace_root: &str,
    path: &str,
    content: &str,
    expected_hash: Option<&str>,
) -> Result<WriteOutcome, WriteWorkspaceError> {
    write_workspace_file_impl_inner(workspace_root, path, content, expected_hash, false)
}

/// No-clobber counterpart for create-only flows such as `.workspace/test_inputs`.
/// The final publish uses a hard link from a sibling temp file so target
/// existence is checked atomically by the filesystem instead of via read-then-write.
pub fn create_workspace_file_if_absent_impl(
    workspace_root: &str,
    path: &str,
    content: &str,
) -> Result<WriteOutcome, WriteWorkspaceError> {
    write_workspace_file_impl_inner(workspace_root, path, content, None, true)
}

fn write_workspace_file_impl_inner(
    workspace_root: &str,
    path: &str,
    content: &str,
    expected_hash: Option<&str>,
    create_if_absent: bool,
) -> Result<WriteOutcome, WriteWorkspaceError> {
    let root = PathBuf::from(workspace_root.trim());
    let target = safe_join(&root, path).map_err(write_failed)?;
    ensure_existing_path_components_inside_workspace(&root, path).map_err(write_failed)?;

    if create_if_absent {
        if target.exists() {
            return Err(write_failed(format!("file already exists: {path}")));
        }
    } else {
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
    }

    if let Some(parent) = target.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| write_failed(format!("cannot create parent dir: {error}")))?;
    }
    ensure_final_parent_inside_workspace(&root, path).map_err(write_failed)?;

    // Atomic publish: write a sibling temp file then rename over the target.
    let mut temp_os = target.clone().into_os_string();
    temp_os.push(".native-tmp");
    let temp = PathBuf::from(temp_os);
    let mut temp_file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temp)
        .map_err(|error| write_failed(format!("cannot write temp file: {error}")))?;
    if let Err(error) = temp_file.write_all(content.as_bytes()) {
        let _ = std::fs::remove_file(&temp);
        return Err(write_failed(format!("cannot write temp file: {error}")));
    }
    drop(temp_file);
    ensure_final_parent_inside_workspace(&root, path).map_err(|error| {
        let _ = std::fs::remove_file(&temp);
        write_failed(error)
    })?;
    if create_if_absent {
        match std::fs::hard_link(&temp, &target) {
            Ok(()) => {
                let _ = std::fs::remove_file(&temp);
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                let _ = std::fs::remove_file(&temp);
                return Err(write_failed(format!("file already exists: {path}")));
            }
            Err(error) => {
                let _ = std::fs::remove_file(&temp);
                return Err(write_failed(format!("cannot finalize create: {error}")));
            }
        }
    } else if let Err(error) = std::fs::rename(&temp, &target) {
        let _ = std::fs::remove_file(&temp);
        return Err(write_failed(format!("cannot finalize write: {error}")));
    }

    Ok(WriteOutcome {
        path: path.to_string(),
        hash: sha256_hex(content),
    })
}

pub fn publish_package_writer_impl(
    workspace_root: &str,
    relative_path: &str,
    request: PublishPackageWriteRequest,
) -> Result<PublishPackageWriteOutcome, PublishPackageWriteError> {
    let root = PathBuf::from(workspace_root.trim());
    let target = safe_join(&root, relative_path)
        .map_err(|message| package_path_escape(relative_path, message))?;
    ensure_existing_path_components_inside_workspace(&root, relative_path)
        .map_err(|message| package_path_escape(relative_path, message))?;

    let parent = target
        .parent()
        .ok_or_else(|| PublishPackageWriteError::PathEscape {
            message: format!("path has no parent: {}", relative_path.trim()),
            path: relative_path.to_string(),
        })?;
    std::fs::create_dir_all(parent)
        .map_err(|error| package_io_error(relative_path, "cannot create package parent", error))?;
    ensure_final_parent_inside_workspace(&root, relative_path)
        .map_err(|message| package_path_escape(relative_path, message))?;

    if target.exists() {
        return Err(PublishPackageWriteError::Conflict {
            message: format!("package target already exists: {}", relative_path.trim()),
            path: relative_path.to_string(),
        });
    }

    let package = serde_json::json!({
        "schema": "studio.publish.package.v1",
        "release_version": request.release_version,
        "content_hash": request.content_hash,
        "manifest_ref": request.manifest_ref,
        "artifact_ref": request.artifact_ref,
    });
    let bytes =
        serde_json::to_vec(&package).map_err(|error| PublishPackageWriteError::IoFailed {
            message: format!("cannot encode publish package: {error}"),
            path: relative_path.to_string(),
        })?;

    let file_name = target
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("publish-package");
    let temp = parent.join(format!(
        ".{file_name}.{}.native-package-tmp",
        std::process::id()
    ));
    {
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temp)
            .map_err(|error| {
                package_io_error(relative_path, "cannot create package temp file", error)
            })?;
        file.write_all(&bytes).map_err(|error| {
            package_io_error(relative_path, "cannot write package temp file", error)
        })?;
        file.sync_all().map_err(|error| {
            package_io_error(relative_path, "cannot sync package temp file", error)
        })?;
    }

    if let Err(error) = std::fs::hard_link(&temp, &target) {
        let _ = std::fs::remove_file(&temp);
        return Err(package_io_error(
            relative_path,
            "cannot publish package without clobbering target",
            error,
        ));
    }
    let native_path = target
        .canonicalize()
        .map_err(|error| package_io_error(relative_path, "cannot resolve package target", error))?
        .to_string_lossy()
        .to_string();
    std::fs::remove_file(&temp).map_err(|error| {
        package_io_error(relative_path, "cannot remove package temp file", error)
    })?;

    let package_text =
        String::from_utf8(bytes).map_err(|error| PublishPackageWriteError::IoFailed {
            message: format!("cannot decode publish package for hash: {error}"),
            path: relative_path.to_string(),
        })?;
    Ok(PublishPackageWriteOutcome {
        path: relative_path.to_string(),
        native_path,
        hash: sha256_hex(&package_text),
        bytes_written: package_text.as_bytes().len() as u64,
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
    root.join(checkpoint_relative_path(rel))
}

fn checkpoint_relative_path(rel: &str) -> String {
    format!("{CHECKPOINT_DIR}/{}.json", sha256_hex(rel))
}

fn write_atomic(target: &Path, bytes: &str) -> Result<(), String> {
    if let Some(parent) = target.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("cannot create parent dir: {error}"))?;
    }
    let mut temp_os = target.to_path_buf().into_os_string();
    temp_os.push(".native-tmp");
    let temp = PathBuf::from(temp_os);
    let mut temp_file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temp)
        .map_err(|error| format!("cannot write temp file: {error}"))?;
    if let Err(error) = temp_file.write_all(bytes.as_bytes()) {
        let _ = std::fs::remove_file(&temp);
        return Err(format!("cannot write temp file: {error}"));
    }
    drop(temp_file);
    if let Err(error) = std::fs::rename(&temp, target) {
        let _ = std::fs::remove_file(&temp);
        return Err(format!("cannot finalize write: {error}"));
    }
    Ok(())
}

fn read_checkpoint_record(root: &Path, path: &str) -> Result<CheckpointRecord, String> {
    let trimmed = path.trim();
    let ckpt_rel = checkpoint_relative_path(trimmed);
    ensure_existing_path_components_inside_workspace(root, &ckpt_rel)?;
    let ckpt = safe_join(root, &ckpt_rel)?;
    let serialized = std::fs::read_to_string(&ckpt).map_err(|error| {
        if error.kind() == std::io::ErrorKind::NotFound {
            format!("no checkpoint to restore for: {path}")
        } else {
            format!("cannot read checkpoint: {error}")
        }
    })?;
    serde_json::from_str(&serialized).map_err(|error| format!("corrupt checkpoint record: {error}"))
}

fn write_checkpoint_record(root: &Path, path: &str, serialized: &str) -> Result<(), String> {
    let ckpt_rel = checkpoint_relative_path(path.trim());
    ensure_existing_path_components_inside_workspace(root, &ckpt_rel)?;
    let ckpt = safe_join(root, &ckpt_rel)?;
    if let Some(parent) = ckpt.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("cannot create parent dir: {error}"))?;
    }
    ensure_final_parent_inside_workspace(root, &ckpt_rel)?;
    write_atomic(&ckpt, serialized)
}

fn remove_checkpoint_record(root: &Path, path: &str) -> Result<(), String> {
    let ckpt_rel = checkpoint_relative_path(path.trim());
    ensure_existing_path_components_inside_workspace(root, &ckpt_rel)?;
    let ckpt = safe_join(root, &ckpt_rel)?;
    match std::fs::remove_file(&ckpt) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(format!("cannot clear checkpoint: {error}")),
    }
}

fn write_restore_atomic(
    root: &Path,
    path: &str,
    target: &Path,
    content: &str,
) -> Result<(), String> {
    ensure_existing_path_components_inside_workspace(root, path)?;
    if let Some(parent) = target.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("cannot create parent dir: {error}"))?;
    }
    ensure_final_parent_inside_workspace(root, path)?;
    write_atomic(target, content)
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
    ensure_existing_path_components_inside_workspace(&root, path)?;
    let ckpt = checkpoint_path(&root, path.trim());

    if ckpt.is_file() {
        let record = read_checkpoint_record(&root, path)?;
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
    write_checkpoint_record(&root, path, &serialized)?;
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
    ensure_existing_path_components_inside_workspace(&root, path)?;
    ensure_existing_path_components_inside_workspace(
        &root,
        &checkpoint_relative_path(path.trim()),
    )?;
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
    write_checkpoint_record(&root, path, &serialized)?;
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

    let record = read_checkpoint_record(&root, path)?;

    if record.existed {
        write_restore_atomic(&root, path, &target, &record.content)?;
    } else {
        ensure_existing_path_components_inside_workspace(&root, path)?;
        match std::fs::symlink_metadata(&target) {
            Ok(_) => std::fs::remove_file(&target)
                .map_err(|error| format!("cannot remove pending new file on restore: {error}"))?,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(format!(
                    "cannot inspect pending new file on restore: {error}"
                ));
            }
        }
    }
    remove_checkpoint_record(&root, path)
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
    ensure_existing_path_components_inside_workspace(&root, path)?;
    remove_checkpoint_record(&root, path)
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
    ensure_existing_path_components_inside_workspace(&root, path)?;
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

enum AllowedDeleteTarget {
    TestInputJson,
    GoldenBaselineDir,
}

fn allowed_delete_target(path: &str) -> Result<AllowedDeleteTarget, String> {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return Err("path is required".to_string());
    }
    let mut parts = Vec::new();
    for component in Path::new(trimmed).components() {
        match component {
            Component::Normal(part) => parts.push(part.to_string_lossy().to_string()),
            Component::CurDir
            | Component::ParentDir
            | Component::RootDir
            | Component::Prefix(_) => {
                return Err(format!("delete path not allowed: {trimmed}"));
            }
        }
    }

    if parts.len() == 3 && parts[0] == ".workspace" && parts[1] == "test_inputs" {
        let file_name = &parts[2];
        if let Some(stem) = file_name.strip_suffix(".json") {
            if is_safe_test_input_name(stem) {
                return Ok(AllowedDeleteTarget::TestInputJson);
            }
        }
    }

    if parts.len() == 3
        && parts[0] == ".workspace"
        && parts[1] == "golden"
        && is_safe_golden_baseline_id(&parts[2])
    {
        return Ok(AllowedDeleteTarget::GoldenBaselineDir);
    }

    Err(format!("delete path not allowed: {trimmed}"))
}

fn is_safe_test_input_name(name: &str) -> bool {
    if name.is_empty() || name.len() > 100 {
        return false;
    }
    let mut chars = name.chars();
    let first = match chars.next() {
        Some(value) => value,
        None => return false,
    };
    if !first.is_ascii_alphanumeric() {
        return false;
    }
    chars.all(|value| value.is_ascii_alphanumeric() || value == '.' || value == '_' || value == '-')
}

fn is_safe_golden_baseline_id(id: &str) -> bool {
    if id.is_empty() || id == "." || id == ".." {
        return false;
    }
    let mut chars = id.chars();
    let first = match chars.next() {
        Some(value) => value,
        None => return false,
    };
    if !(first.is_ascii_alphanumeric() || first == '_') {
        return false;
    }
    chars.all(|value| {
        value.is_ascii_alphanumeric()
            || value == '.'
            || value == '_'
            || value == '-'
            || value == ':'
    })
}

/// Delete only the native-fs surfaces currently exposed by Studio:
/// `.workspace/test_inputs/<safe>.json` files and `.workspace/golden/<safe-id>`
/// baseline directories. This avoids exposing a general recursive delete.
pub fn delete_workspace_path_impl(workspace_root: &str, path: &str) -> Result<(), String> {
    let allowed = allowed_delete_target(path)?;
    let root = PathBuf::from(workspace_root.trim());
    let target = safe_join(&root, path)?;
    ensure_existing_path_components_inside_workspace(&root, path)?;
    let metadata = std::fs::symlink_metadata(&target).map_err(|error| {
        if error.kind() == std::io::ErrorKind::NotFound {
            format!("path not found: {path}")
        } else {
            format!("cannot inspect workspace path: {error}")
        }
    })?;
    let file_type = metadata.file_type();
    match allowed {
        AllowedDeleteTarget::TestInputJson => {
            if !file_type.is_file() {
                return Err(format!("delete path must be a file: {path}"));
            }
            std::fs::remove_file(&target).map_err(|error| format!("cannot remove file: {error}"))
        }
        AllowedDeleteTarget::GoldenBaselineDir => {
            if !file_type.is_dir() {
                return Err(format!("delete path must be a directory: {path}"));
            }
            std::fs::remove_dir_all(&target).map_err(|error| format!("cannot remove dir: {error}"))
        }
    }
}

fn golden_baseline_id_for_file(path: &str, expected_file_name: &str) -> Result<String, String> {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return Err("golden baseline path is required".to_string());
    }
    let mut parts = Vec::new();
    for component in Path::new(trimmed).components() {
        match component {
            Component::Normal(part) => parts.push(part.to_string_lossy().to_string()),
            Component::CurDir
            | Component::ParentDir
            | Component::RootDir
            | Component::Prefix(_) => {
                return Err(format!("golden baseline path not allowed: {trimmed}"));
            }
        }
    }
    if parts.len() != 4
        || parts[0] != ".workspace"
        || parts[1] != "golden"
        || parts[3] != expected_file_name
        || !is_safe_golden_baseline_id(&parts[2])
    {
        return Err(format!("golden baseline path not allowed: {trimmed}"));
    }
    Ok(parts[2].clone())
}

fn validate_golden_baseline_paths(
    result_path: &str,
    metadata_path: &str,
) -> Result<String, String> {
    let result_id = golden_baseline_id_for_file(result_path, "result.json")?;
    let metadata_id = golden_baseline_id_for_file(metadata_path, "golden_metadata.json")?;
    if result_id != metadata_id {
        return Err("golden baseline paths must target the same baseline id".to_string());
    }
    Ok(result_id)
}

fn unique_sibling_path(target: &Path, label: &str) -> Result<PathBuf, String> {
    let file_name = target
        .file_name()
        .ok_or_else(|| format!("path has no file name: {}", target.display()))?
        .to_string_lossy();
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or(0);
    Ok(target.with_file_name(format!(
        ".{file_name}.native-{label}-{}-{nanos}",
        std::process::id()
    )))
}

fn write_golden_temp_file(target: &Path, label: &str, content: &str) -> Result<PathBuf, String> {
    let temp = unique_sibling_path(target, label)?;
    let mut temp_file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temp)
        .map_err(|error| format!("cannot write golden temp file: {error}"))?;
    if let Err(error) = temp_file.write_all(content.as_bytes()) {
        let _ = std::fs::remove_file(&temp);
        return Err(format!("cannot write golden temp file: {error}"));
    }
    drop(temp_file);
    Ok(temp)
}

#[derive(Debug)]
struct PublishedGoldenFile {
    target: PathBuf,
    backup: Option<PathBuf>,
}

fn publish_golden_file(target: &Path, temp: &Path) -> Result<PublishedGoldenFile, String> {
    let backup = match std::fs::symlink_metadata(target) {
        Ok(metadata) => {
            if !metadata.file_type().is_file() {
                return Err(format!(
                    "golden target must be a regular file: {}",
                    target.display()
                ));
            }
            let backup = unique_sibling_path(target, "backup")?;
            std::fs::rename(target, &backup)
                .map_err(|error| format!("cannot backup golden file: {error}"))?;
            Some(backup)
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => None,
        Err(error) => return Err(format!("cannot inspect golden file: {error}")),
    };

    if let Err(error) = std::fs::rename(temp, target) {
        if let Some(backup_path) = &backup {
            let _ = std::fs::rename(backup_path, target);
        }
        return Err(format!("cannot publish golden file: {error}"));
    }

    Ok(PublishedGoldenFile {
        target: target.to_path_buf(),
        backup,
    })
}

fn rollback_published_golden_file(published: &PublishedGoldenFile) -> Result<(), String> {
    match std::fs::symlink_metadata(&published.target) {
        Ok(metadata) => {
            if metadata.file_type().is_file() || metadata.file_type().is_symlink() {
                std::fs::remove_file(&published.target)
                    .map_err(|error| format!("cannot remove partial golden file: {error}"))?;
            } else {
                return Err(format!(
                    "partial golden target is not a file: {}",
                    published.target.display()
                ));
            }
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(error) => return Err(format!("cannot inspect partial golden file: {error}")),
    }

    if let Some(backup) = &published.backup {
        if backup.exists() {
            std::fs::rename(backup, &published.target)
                .map_err(|error| format!("cannot restore golden backup: {error}"))?;
        }
    }
    Ok(())
}

fn remove_golden_backup(published: &PublishedGoldenFile) -> Result<(), String> {
    if let Some(backup) = &published.backup {
        match std::fs::remove_file(backup) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(format!("cannot remove golden backup: {error}")),
        }
    }
    Ok(())
}

fn remove_empty_baseline_dir_if_new(baseline_preexisted: bool, baseline_dir: &Path) {
    if !baseline_preexisted {
        let _ = std::fs::remove_dir(baseline_dir);
    }
}

pub fn write_golden_baseline_impl(
    workspace_root: &str,
    result_path: &str,
    result_content: &str,
    metadata_path: &str,
    metadata_content: &str,
) -> Result<(), String> {
    write_golden_baseline_impl_inner(
        workspace_root,
        result_path,
        result_content,
        metadata_path,
        metadata_content,
        false,
    )
}

#[cfg(test)]
fn write_golden_baseline_impl_for_test(
    workspace_root: &str,
    result_path: &str,
    result_content: &str,
    metadata_path: &str,
    metadata_content: &str,
    inject_metadata_publish_failure: bool,
) -> Result<(), String> {
    write_golden_baseline_impl_inner(
        workspace_root,
        result_path,
        result_content,
        metadata_path,
        metadata_content,
        inject_metadata_publish_failure,
    )
}

fn write_golden_baseline_impl_inner(
    workspace_root: &str,
    result_path: &str,
    result_content: &str,
    metadata_path: &str,
    metadata_content: &str,
    inject_metadata_publish_failure: bool,
) -> Result<(), String> {
    validate_golden_baseline_paths(result_path, metadata_path)?;
    let root = PathBuf::from(workspace_root.trim());
    let result_target = safe_join(&root, result_path)?;
    let metadata_target = safe_join(&root, metadata_path)?;
    ensure_existing_path_components_inside_workspace(&root, result_path)?;
    ensure_existing_path_components_inside_workspace(&root, metadata_path)?;

    let baseline_dir = result_target
        .parent()
        .ok_or_else(|| format!("path has no parent: {}", result_path.trim()))?
        .to_path_buf();
    if metadata_target.parent() != Some(baseline_dir.as_path()) {
        return Err("golden baseline files must share the same directory".to_string());
    }
    let baseline_preexisted = std::fs::symlink_metadata(&baseline_dir).is_ok();
    std::fs::create_dir_all(&baseline_dir)
        .map_err(|error| format!("cannot create golden baseline dir: {error}"))?;
    ensure_final_parent_inside_workspace(&root, result_path)?;
    ensure_final_parent_inside_workspace(&root, metadata_path)?;

    let result_temp = match write_golden_temp_file(&result_target, "result", result_content) {
        Ok(temp) => temp,
        Err(error) => {
            remove_empty_baseline_dir_if_new(baseline_preexisted, &baseline_dir);
            return Err(error);
        }
    };
    let metadata_temp = match write_golden_temp_file(&metadata_target, "metadata", metadata_content)
    {
        Ok(temp) => temp,
        Err(error) => {
            let _ = std::fs::remove_file(&result_temp);
            remove_empty_baseline_dir_if_new(baseline_preexisted, &baseline_dir);
            return Err(error);
        }
    };

    let published_result = match publish_golden_file(&result_target, &result_temp) {
        Ok(published) => published,
        Err(error) => {
            let _ = std::fs::remove_file(&result_temp);
            let _ = std::fs::remove_file(&metadata_temp);
            remove_empty_baseline_dir_if_new(baseline_preexisted, &baseline_dir);
            return Err(error);
        }
    };

    if inject_metadata_publish_failure {
        let _ = std::fs::remove_file(&metadata_temp);
        let rollback_result = rollback_published_golden_file(&published_result);
        remove_empty_baseline_dir_if_new(baseline_preexisted, &baseline_dir);
        if let Err(error) = rollback_result {
            return Err(format!(
                "injected metadata publish failure; rollback failed: {error}"
            ));
        }
        return Err("injected metadata publish failure".to_string());
    }

    let published_metadata = match publish_golden_file(&metadata_target, &metadata_temp) {
        Ok(published) => published,
        Err(error) => {
            let rollback_result = rollback_published_golden_file(&published_result);
            remove_empty_baseline_dir_if_new(baseline_preexisted, &baseline_dir);
            if let Err(rollback_error) = rollback_result {
                return Err(format!("{error}; rollback failed: {rollback_error}"));
            }
            return Err(error);
        }
    };

    remove_golden_backup(&published_result)?;
    remove_golden_backup(&published_metadata)?;
    Ok(())
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
    ensure_existing_path_components_inside_workspace(&root, relative_dir)?;
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
    relative_path: String,
    content: String,
    expected_hash: Option<String>,
    create_if_absent: Option<bool>,
) -> Result<WriteOutcome, WriteWorkspaceError> {
    let config_dir = crate::resolve_config_dir();
    let resolved = resolve_workspace_root(&workspace_root, &config_dir).map_err(write_failed)?;
    if create_if_absent.unwrap_or(false) {
        create_workspace_file_if_absent_impl(&resolved.to_string_lossy(), &relative_path, &content)
    } else {
        write_workspace_file_impl(
            &resolved.to_string_lossy(),
            &relative_path,
            &content,
            expected_hash.as_deref(),
        )
    }
}

#[tauri::command]
pub fn publish_package_writer(
    workspace_root: String,
    relative_path: String,
    release_version: String,
    content_hash: String,
    manifest_ref: String,
    artifact_ref: serde_json::Value,
) -> Result<PublishPackageWriteOutcome, PublishPackageWriteError> {
    let config_dir = crate::resolve_config_dir();
    let resolved = resolve_workspace_root(&workspace_root, &config_dir)
        .map_err(|message| package_path_escape(&relative_path, message))?;
    publish_package_writer_impl(
        &resolved.to_string_lossy(),
        &relative_path,
        PublishPackageWriteRequest {
            release_version,
            content_hash,
            manifest_ref,
            artifact_ref,
        },
    )
}

#[tauri::command]
pub fn write_golden_baseline(
    workspace_root: String,
    result_path: String,
    result_content: String,
    metadata_path: String,
    metadata_content: String,
) -> Result<(), String> {
    let config_dir = crate::resolve_config_dir();
    let resolved = resolve_workspace_root(&workspace_root, &config_dir)?;
    write_golden_baseline_impl(
        &resolved.to_string_lossy(),
        &result_path,
        &result_content,
        &metadata_path,
        &metadata_content,
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
pub fn delete_workspace_path(workspace_root: String, path: String) -> Result<(), String> {
    let config_dir = crate::resolve_config_dir();
    let resolved = resolve_workspace_root(&workspace_root, &config_dir)?;
    delete_workspace_path_impl(&resolved.to_string_lossy(), &path)
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

// ── New-skill / Open-folder native-fs (D12: Rust sole writer for build-dir +
//    scaffold + git init + skill_index) ───────────────────────────────────────
//
// These move the new/open flows off the Python `POST /api/skills` writer onto
// the native-fs Rust sole writer (D12). They build the skill dir, write the
// scaffold byte-faithfully to the current Python `_SCAFFOLD_FILES` (the
// logic-phase template; the D-1-4 agent-phase template is not yet defined), run
// `git init` faithfully to Python `initialize_skill_repository`, and write the
// `skill_index.json` entry byte-for-byte to Python `_write_skill_index` so the
// read-detail sidecar `GET /api/skills/{id}` still resolves id→dir. They do NOT
// register to a backend registry and do NOT validate the manifest (D2).

/// Studio `.gitignore` body — byte-for-byte to Python `STUDIO_GITIGNORE`
/// (services/git_local.py). Faithful copy so the initial commit and config
/// arbitration stay identical across writers.
const STUDIO_GITIGNORE: &str =
    "/.workspace/*\n!/.workspace/golden/\n/.workspace/local_settings.json\n";

/// Fallback git author when `app_settings.json` has no `user_id` — byte-for-byte
/// to Python `FALLBACK_USER_ID` (services/git_local.py).
const FALLBACK_USER_ID: &str = "studio-user";

#[derive(Serialize, Debug)]
pub struct SkillWorkspaceOutcome {
    pub root: String,
    pub skill_id: String,
}

/// The current logic-phase scaffold, byte-for-byte to Python `_SCAFFOLD_FILES`
/// (services/skills.py) with `name: new-skill` substituted to `name: <skill_id>`
/// in GRAPH.md, exactly like Python `_scaffold_files_for`. Returned as
/// (relative_posix_path, content) pairs.
fn scaffold_files_for(skill_id: &str) -> Vec<(String, String)> {
    let graph_md = format!(
        "---\nschema_version: \"v0.3.0\"\nname: {skill_id}\ndescription: \"New Studio skill\"\nio:\n  inputs:\n    type: object\n    properties: {{}}\n  outputs:\n    type: object\n    properties: {{}}\nphases:\n  - init\n---\n<phase depends_on=\"input\" output>init</phase>\n"
    );
    let logic_md = "---\nio:\n  inputs:\n    type: object\n    properties: {}\n  outputs:\n    type: object\n    properties: {}\n---\n<action>initialize</action>\n\n# init phase logic\n\nDescribe what this phase does.\n".to_string();
    let initialize_py =
        "def initialize(context):\n    \"\"\"Starter logic action for a new Studio skill.\"\"\"\n    return None\n"
            .to_string();
    vec![
        ("GRAPH.md".to_string(), graph_md),
        ("phases/init/LOGIC.md".to_string(), logic_md),
        ("phases/init/actions/initialize.py".to_string(), initialize_py),
    ]
}

/// Derive a workspace skill id from a folder path. Byte-for-byte port of the
/// frontend `skillIdFromWorkspaceRoot` (components/studio/workspace-identity.ts)
/// so the id Rust writes into `skill_index.json` equals the id the frontend
/// decodes from the `local-workspace:` selection token — keeping a single
/// derivation source across the boundary. Parity is asserted in tests.
fn skill_id_from_workspace_root(path: &str) -> String {
    let name = last_path_segment(path).unwrap_or("imported-skill");
    let normalized = normalize_skill_id_segment(name);
    let with_letter = if starts_with_ascii_letter(&normalized) {
        normalized
    } else {
        format!("skill-{normalized}")
    };
    if with_letter.is_empty() {
        "imported-skill".to_string()
    } else {
        with_letter
    }
}

fn last_path_segment(path: &str) -> Option<&str> {
    let mut last: Option<&str> = None;
    let mut start = 0usize;
    let bytes = path.as_bytes();
    let mut segment_end = 0usize;
    let mut have_segment = false;
    for (idx, ch) in path.char_indices() {
        if ch == '/' || ch == '\\' {
            if have_segment {
                last = Some(&path[start..segment_end]);
            }
            start = idx + ch.len_utf8();
            have_segment = false;
        } else {
            segment_end = idx + ch.len_utf8();
            have_segment = true;
        }
    }
    if have_segment {
        Some(&path[start..])
    } else {
        last
    }
    .filter(|segment| !segment.is_empty())
}

fn normalize_skill_id_segment(name: &str) -> String {
    let mut normalized = String::new();
    for ch in name.chars() {
        let lower = ch.to_ascii_lowercase();
        if lower.is_ascii_alphanumeric() {
            normalized.push(lower);
        } else if !normalized.is_empty() && !normalized.ends_with('-') {
            normalized.push('-');
        }
    }
    if normalized.ends_with('-') {
        normalized.pop();
    }
    normalized
}

fn starts_with_ascii_letter(value: &str) -> bool {
    value.chars().next().is_some_and(|c| c.is_ascii_alphabetic())
}

/// Resolve the new-skill parent dir. Byte-for-byte to Python `_default_skills_root`
/// + `create_new_skill` parent handling: a blank parent falls back to
/// `app_settings.json:default_skills_directory` (when set) else `<config_dir>/Skills`
/// (Python `default_skills_root`); a non-blank parent is used as-is and must exist.
fn resolve_new_skill_parent(parent_directory: &str, config_dir: &Path) -> Result<PathBuf, String> {
    let trimmed = parent_directory.trim();
    if trimmed.is_empty() {
        return Ok(default_skills_root(config_dir));
    }
    let parent = PathBuf::from(trimmed);
    if !parent.is_dir() {
        return Err(format!("parent directory does not exist: {trimmed}"));
    }
    Ok(parent)
}

fn default_skills_root(config_dir: &Path) -> PathBuf {
    if let Some(custom) = app_settings_default_skills_directory(config_dir) {
        return custom;
    }
    config_dir.join("Skills")
}

/// Read `default_skills_directory` from `<config_dir>/app_settings.json`, mirroring
/// Python `_default_skills_root` reading `AppSettings.default_skills_directory`.
fn app_settings_default_skills_directory(config_dir: &Path) -> Option<PathBuf> {
    let raw = std::fs::read_to_string(config_dir.join("app_settings.json")).ok()?;
    let payload: serde_json::Value = serde_json::from_str(&raw).ok()?;
    let value = payload.get("default_skills_directory")?.as_str()?.trim();
    if value.is_empty() {
        return None;
    }
    Some(PathBuf::from(value))
}

fn directory_is_nonempty(path: &Path) -> bool {
    match std::fs::read_dir(path) {
        Ok(mut entries) => entries.next().is_some(),
        Err(_) => false,
    }
}

/// Read the git author id from `<config_dir>/app_settings.json`, byte-for-byte to
/// Python `_read_user_id_from_app_settings` (keys `user_id`/`User ID`/`userId`).
fn read_user_id_from_app_settings(config_dir: &Path) -> Option<String> {
    let raw = std::fs::read_to_string(config_dir.join("app_settings.json")).ok()?;
    let payload: serde_json::Value = serde_json::from_str(&raw).ok()?;
    let object = payload.as_object()?;
    for key in ["user_id", "User ID", "userId"] {
        if let Some(value) = object.get(key).and_then(|value| value.as_str()) {
            let trimmed = value.trim();
            if !trimmed.is_empty() {
                return Some(trimmed.to_string());
            }
        }
    }
    None
}

fn run_git(skill_dir: &Path, args: &[&str]) -> Result<(), String> {
    let output = std::process::Command::new("git")
        .args(args)
        .current_dir(skill_dir)
        .output()
        .map_err(|error| format!("git {} failed to spawn: {error}", args.join(" ")))?;
    if !output.status.success() {
        return Err(format!(
            "git {} failed: {}",
            args.join(" "),
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    Ok(())
}

/// Initialize local git, faithful to Python `initialize_skill_repository`:
/// write `.gitignore`, `git init`, set local `user.name`/`user.email` from the
/// resolved user id (fallback `studio-user` with a warning, email
/// `<id>@studio.local`), `git add -A`, and commit `initial-skill` only when the
/// working tree has staged content.
fn initialize_skill_repository(skill_dir: &Path, config_dir: &Path) -> Result<(), String> {
    std::fs::write(skill_dir.join(".gitignore"), STUDIO_GITIGNORE)
        .map_err(|error| format!("cannot write .gitignore: {error}"))?;
    run_git(skill_dir, &["init"])?;
    let user_id = read_user_id_from_app_settings(config_dir).unwrap_or_else(|| {
        log::warn!("native_fs.initialize_skill_repository: user_id missing, using fallback");
        FALLBACK_USER_ID.to_string()
    });
    run_git(skill_dir, &["config", "--local", "user.name", &user_id])?;
    let email = format!("{user_id}@studio.local");
    run_git(skill_dir, &["config", "--local", "user.email", &email])?;
    run_git(skill_dir, &["add", "-A"])?;
    if git_has_staged_changes(skill_dir)? {
        run_git(skill_dir, &["commit", "-m", "initial-skill"])?;
    }
    Ok(())
}

/// True when `git status --porcelain` reports any entry — mirrors the Python
/// `service.status(...).stdout.strip()` guard before committing `initial-skill`.
fn git_has_staged_changes(skill_dir: &Path) -> Result<bool, String> {
    let output = std::process::Command::new("git")
        .args(["status", "--porcelain"])
        .current_dir(skill_dir)
        .output()
        .map_err(|error| format!("git status failed to spawn: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "git status failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    Ok(!String::from_utf8_lossy(&output.stdout).trim().is_empty())
}

/// Upsert one `skill_index.json` entry, serialized byte-for-byte to Python
/// `_write_skill_index` (metadata_local.py): a JSON object keyed by skill id,
/// each value `{absolute_path, l2_remote_url}`, dumped with sorted keys + 2-space
/// indent + a single trailing newline. serde_json's default `Map` is a `BTreeMap`,
/// so both the top-level ids and the per-entry keys serialize in sorted order,
/// matching Python `sort_keys=True`.
fn upsert_skill_index_entry(config_dir: &Path, skill_id: &str, absolute_path: &str) -> Result<(), String> {
    let index_path = config_dir.join("skill_index.json");
    let mut index = read_skill_index(&index_path);
    let mut entry = serde_json::Map::new();
    entry.insert(
        "absolute_path".to_string(),
        serde_json::Value::String(absolute_path.to_string()),
    );
    entry.insert(
        "l2_remote_url".to_string(),
        serde_json::Value::String(String::new()),
    );
    index.insert(skill_id.to_string(), serde_json::Value::Object(entry));
    write_skill_index(&index_path, &index)
}

/// Read the existing skill index, normalizing each entry to the
/// `{absolute_path, l2_remote_url}` shape Python persists (drops malformed
/// entries, defaults a missing/non-string `l2_remote_url` to ""), so a re-write
/// is byte-stable against the Python writer.
fn read_skill_index(index_path: &Path) -> serde_json::Map<String, serde_json::Value> {
    let mut normalized = serde_json::Map::new();
    let raw = match std::fs::read_to_string(index_path) {
        Ok(raw) => raw,
        Err(_) => return normalized,
    };
    let parsed: serde_json::Value = match serde_json::from_str(&raw) {
        Ok(value) => value,
        Err(error) => {
            log::warn!(
                "native_fs.read_skill_index: corrupt {}, starting empty: {error}",
                index_path.display()
            );
            return normalized;
        }
    };
    let object = match parsed.as_object() {
        Some(object) => object,
        None => return normalized,
    };
    for (skill_id, value) in object {
        let entry = match value.as_object() {
            Some(entry) => entry,
            None => continue,
        };
        let absolute_path = match entry.get("absolute_path").and_then(|value| value.as_str()) {
            Some(path) if !path.is_empty() => path.to_string(),
            _ => continue,
        };
        let l2_remote_url = entry
            .get("l2_remote_url")
            .and_then(|value| value.as_str())
            .unwrap_or("")
            .to_string();
        let mut normalized_entry = serde_json::Map::new();
        normalized_entry.insert(
            "absolute_path".to_string(),
            serde_json::Value::String(absolute_path),
        );
        normalized_entry.insert(
            "l2_remote_url".to_string(),
            serde_json::Value::String(l2_remote_url),
        );
        normalized.insert(skill_id.clone(), serde_json::Value::Object(normalized_entry));
    }
    normalized
}

fn write_skill_index(
    index_path: &Path,
    index: &serde_json::Map<String, serde_json::Value>,
) -> Result<(), String> {
    if let Some(parent) = index_path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("cannot create config dir: {error}"))?;
    }
    // PrettyFormatter defaults to 2-space indent, matching Python json.dumps(indent=2).
    let serialized = serde_json::to_string_pretty(&serde_json::Value::Object(index.clone()))
        .map_err(|error| format!("cannot serialize skill index: {error}"))?;
    std::fs::write(index_path, format!("{serialized}\n"))
        .map_err(|error| format!("cannot write skill index: {error}"))
}

/// Build a new skill on disk (D12 sole writer): validate id, resolve parent,
/// reject a non-empty target, write the scaffold + `.workspace/`, run `git init`,
/// and write the `skill_index.json` entry. Returns `{root, skill_id}`.
pub fn create_skill_workspace_impl(
    parent_directory: &str,
    skill_id: &str,
    config_dir: &Path,
) -> Result<SkillWorkspaceOutcome, String> {
    if !is_valid_default_workspace_skill_id(skill_id) {
        return Err(format!("invalid skill id: {skill_id}"));
    }
    let parent = resolve_new_skill_parent(parent_directory, config_dir)?;
    let skill_dir = parent.join(skill_id);
    if skill_dir.exists() && directory_is_nonempty(&skill_dir) {
        return Err(format!(
            "Cannot create a new skill in a non-empty folder: {}",
            skill_dir.display()
        ));
    }
    std::fs::create_dir_all(&skill_dir)
        .map_err(|error| format!("cannot create skill dir: {error}"))?;

    for (rel_path, content) in scaffold_files_for(skill_id) {
        let target = safe_join(&skill_dir, &rel_path)?;
        if let Some(file_parent) = target.parent() {
            std::fs::create_dir_all(file_parent)
                .map_err(|error| format!("cannot create scaffold dir: {error}"))?;
        }
        std::fs::write(&target, content)
            .map_err(|error| format!("cannot write scaffold file {rel_path}: {error}"))?;
    }
    std::fs::create_dir_all(skill_dir.join(".workspace"))
        .map_err(|error| format!("cannot create .workspace dir: {error}"))?;

    initialize_skill_repository(&skill_dir, config_dir)?;

    let root = skill_dir.to_string_lossy().to_string();
    upsert_skill_index_entry(config_dir, skill_id, &root)?;
    Ok(SkillWorkspaceOutcome {
        root,
        skill_id: skill_id.to_string(),
    })
}

/// Register an opened folder as a workspace (D2: OS checks only, no manifest
/// validation): verify it exists and is a directory, derive the skill id from the
/// path, write the `skill_index.json` entry, and return `{root, skill_id}`.
pub fn open_skill_workspace_impl(
    directory: &str,
    config_dir: &Path,
) -> Result<SkillWorkspaceOutcome, String> {
    let trimmed = directory.trim();
    if trimmed.is_empty() {
        return Err("directory is required".to_string());
    }
    let dir = PathBuf::from(trimmed);
    if !dir.exists() {
        return Err(format!("directory does not exist: {trimmed}"));
    }
    if !dir.is_dir() {
        return Err(format!("not a directory: {trimmed}"));
    }
    let root = dir.to_string_lossy().to_string();
    let skill_id = skill_id_from_workspace_root(&root);
    upsert_skill_index_entry(config_dir, &skill_id, &root)?;
    Ok(SkillWorkspaceOutcome { root, skill_id })
}

/// Read-only existence check for stale-MRU pruning. No side effects.
pub fn workspace_path_exists_impl(path: &str) -> bool {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return false;
    }
    Path::new(trimmed).exists()
}

#[tauri::command]
pub fn create_skill_workspace(
    parent_directory: String,
    skill_id: String,
) -> Result<SkillWorkspaceOutcome, String> {
    let config_dir = crate::resolve_config_dir();
    create_skill_workspace_impl(&parent_directory, &skill_id, &config_dir)
}

#[tauri::command]
pub fn open_skill_workspace(directory: String) -> Result<SkillWorkspaceOutcome, String> {
    let config_dir = crate::resolve_config_dir();
    open_skill_workspace_impl(&directory, &config_dir)
}

#[tauri::command]
pub fn workspace_path_exists(path: String) -> Result<bool, String> {
    Ok(workspace_path_exists_impl(&path))
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

    #[cfg(unix)]
    fn symlink_path(target: &Path, link: &Path) {
        std::os::unix::fs::symlink(target, link).expect("symlink");
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
    fn create_workspace_file_if_absent_refuses_to_overwrite_existing_file() {
        let root = temp_root("write-create-existing");
        std::fs::create_dir_all(root.join(".workspace/test_inputs")).unwrap();
        std::fs::write(
            root.join(".workspace/test_inputs/case.json"),
            "{\"existing\":true}",
        )
        .unwrap();

        let error = create_workspace_file_if_absent_impl(
            root.to_str().unwrap(),
            ".workspace/test_inputs/case.json",
            "{\"incoming\":true}",
        )
        .expect_err("existing file must reject no-clobber create");

        match error {
            WriteWorkspaceError::WriteFailed { message } => assert!(
                message.contains("file already exists"),
                "unexpected error: {message}"
            ),
            WriteWorkspaceError::HashConflict { .. } => panic!("unexpected hash conflict"),
        }
        assert_eq!(
            std::fs::read_to_string(root.join(".workspace/test_inputs/case.json")).unwrap(),
            "{\"existing\":true}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn create_workspace_file_if_absent_creates_missing_file() {
        let root = temp_root("write-create-missing");

        let outcome = create_workspace_file_if_absent_impl(
            root.to_str().unwrap(),
            ".workspace/test_inputs/case.json",
            "{\"created\":true}",
        )
        .expect("create missing file");

        assert_eq!(outcome.hash, sha256_hex("{\"created\":true}"));
        assert_eq!(
            std::fs::read_to_string(root.join(".workspace/test_inputs/case.json")).unwrap(),
            "{\"created\":true}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    fn publish_package_request() -> PublishPackageWriteRequest {
        PublishPackageWriteRequest {
            release_version: "1.0.0".to_string(),
            content_hash: format!("sha256:{}", "a".repeat(64)),
            manifest_ref: "product/releases/text-segmentation/1.0.0.json".to_string(),
            artifact_ref: serde_json::json!({
                "artifact_id": "text-segmentation",
                "store": "product",
                "content_hash": format!("sha256:{}", "a".repeat(64)),
                "manifest_ref": "product/manifests/text-segmentation.json",
            }),
        }
    }

    #[test]
    fn publish_package_writer_writes_release_manifest_package_with_hash() {
        let root = temp_root("publish-package-success");
        let outcome = publish_package_writer_impl(
            root.to_str().unwrap(),
            ".workspace/releases/text-segmentation-1.0.0.package.json",
            publish_package_request(),
        )
        .expect("write package");

        let package_path = root.join(".workspace/releases/text-segmentation-1.0.0.package.json");
        let package = std::fs::read_to_string(&package_path).expect("package bytes");
        assert!(package.contains("\"release_version\":\"1.0.0\""));
        assert!(package.contains("\"content_hash\":\"sha256:"));
        assert!(
            package.contains("\"manifest_ref\":\"product/releases/text-segmentation/1.0.0.json\"")
        );
        assert_eq!(
            outcome.path,
            ".workspace/releases/text-segmentation-1.0.0.package.json"
        );
        assert_eq!(
            outcome.native_path,
            package_path.canonicalize().unwrap().to_string_lossy()
        );
        assert_eq!(outcome.hash, sha256_hex(&package));
        assert_eq!(outcome.bytes_written as usize, package.as_bytes().len());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn publish_package_writer_emits_full_publish_package_v1_schema() {
        let root = temp_root("publish-package-schema");
        publish_package_writer_impl(
            root.to_str().unwrap(),
            ".workspace/releases/text-segmentation-1.0.0.package.json",
            publish_package_request(),
        )
        .expect("write package");

        let package_path = root.join(".workspace/releases/text-segmentation-1.0.0.package.json");
        let parsed: serde_json::Value =
            serde_json::from_slice(&std::fs::read(&package_path).expect("package bytes"))
                .expect("package is valid json");

        assert_eq!(parsed["schema"], "studio.publish.package.v1");
        assert_eq!(parsed["release_version"], "1.0.0");
        assert_eq!(parsed["content_hash"], format!("sha256:{}", "a".repeat(64)));
        assert_eq!(
            parsed["manifest_ref"],
            "product/releases/text-segmentation/1.0.0.json"
        );
        // The full artifact_ref object must round-trip into the package, not be
        // flattened or dropped — downstream release runs read it verbatim.
        assert_eq!(parsed["artifact_ref"]["artifact_id"], "text-segmentation");
        assert_eq!(parsed["artifact_ref"]["store"], "product");
        assert_eq!(
            parsed["artifact_ref"]["manifest_ref"],
            "product/manifests/text-segmentation.json"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn publish_package_writer_rejects_parent_traversal() {
        let root = temp_root("publish-package-traversal");
        let error = publish_package_writer_impl(
            root.to_str().unwrap(),
            "../release.package.json",
            publish_package_request(),
        )
        .expect_err("traversal is rejected");

        assert!(matches!(error, PublishPackageWriteError::PathEscape { .. }));
        assert!(!root.join("../release.package.json").exists());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[cfg(unix)]
    #[test]
    fn publish_package_writer_rejects_symlink_parent_escape() {
        let root = temp_root("publish-package-symlink-root");
        let outside = temp_root("publish-package-symlink-outside");
        std::fs::create_dir_all(root.join(".workspace")).unwrap();
        symlink_path(&outside, &root.join(".workspace/releases"));

        let error = publish_package_writer_impl(
            root.to_str().unwrap(),
            ".workspace/releases/release.package.json",
            publish_package_request(),
        )
        .expect_err("symlink escape is rejected");

        assert!(matches!(error, PublishPackageWriteError::PathEscape { .. }));
        assert!(!outside.join("release.package.json").exists());
        let _ = std::fs::remove_dir_all(&root);
        let _ = std::fs::remove_dir_all(&outside);
    }

    #[test]
    fn publish_package_writer_refuses_to_overwrite_existing_target() {
        let root = temp_root("publish-package-conflict");
        let target = root.join(".workspace/releases/release.package.json");
        std::fs::create_dir_all(target.parent().unwrap()).unwrap();
        std::fs::write(&target, "existing").unwrap();

        let error = publish_package_writer_impl(
            root.to_str().unwrap(),
            ".workspace/releases/release.package.json",
            publish_package_request(),
        )
        .expect_err("existing target is a no-clobber conflict");

        assert!(matches!(error, PublishPackageWriteError::Conflict { .. }));
        assert_eq!(std::fs::read_to_string(&target).unwrap(), "existing");
        let _ = std::fs::remove_dir_all(&root);
    }

    #[cfg(unix)]
    #[test]
    fn publish_package_writer_maps_permission_error() {
        use std::os::unix::fs::PermissionsExt;

        let root = temp_root("publish-package-permission");
        let parent = root.join(".workspace/releases");
        std::fs::create_dir_all(&parent).unwrap();
        let original_mode = std::fs::metadata(&parent).unwrap().permissions().mode();
        std::fs::set_permissions(&parent, std::fs::Permissions::from_mode(0o500)).unwrap();

        let error = publish_package_writer_impl(
            root.to_str().unwrap(),
            ".workspace/releases/release.package.json",
            publish_package_request(),
        )
        .expect_err("read-only parent maps to permission");

        std::fs::set_permissions(&parent, std::fs::Permissions::from_mode(original_mode)).unwrap();
        assert!(matches!(
            error,
            PublishPackageWriteError::PermissionDenied { .. }
        ));
        let _ = std::fs::remove_dir_all(&root);
    }

    #[cfg(unix)]
    #[test]
    fn final_parent_check_refuses_symlink_parent_escape() {
        let root = temp_root("write-final-parent-check");
        let outside = temp_root("write-final-parent-outside");
        std::fs::create_dir_all(root.join(".workspace")).unwrap();
        symlink_path(&outside, &root.join(".workspace/test_inputs"));

        let error = ensure_final_parent_inside_workspace(&root, ".workspace/test_inputs/case.json")
            .expect_err("final parent symlink escape rejected");

        assert!(
            error.contains("escapes workspace"),
            "unexpected error: {error}"
        );
        let _ = std::fs::remove_dir_all(&root);
        let _ = std::fs::remove_dir_all(&outside);
    }

    #[cfg(unix)]
    #[test]
    fn write_workspace_file_refuses_symlink_parent_escape() {
        let root = temp_root("write-symlink-parent-escape");
        let outside = temp_root("write-symlink-parent-outside");
        symlink_path(&outside, &root.join("link"));

        let error =
            write_workspace_file_impl(root.to_str().unwrap(), "link/owned.md", "owned", None)
                .expect_err("symlink parent escape rejected");

        match error {
            WriteWorkspaceError::WriteFailed { message } => assert!(
                message.contains("escapes workspace"),
                "unexpected error: {message}"
            ),
            WriteWorkspaceError::HashConflict { .. } => panic!("unexpected hash conflict"),
        }
        assert!(
            !outside.join("owned.md").exists(),
            "write must not create the outside file"
        );
        let _ = std::fs::remove_dir_all(&root);
        let _ = std::fs::remove_dir_all(&outside);
    }

    #[cfg(unix)]
    #[test]
    fn write_workspace_file_refuses_preexisting_temp_symlink_escape() {
        let root = temp_root("write-temp-symlink-escape");
        let outside = temp_root("write-temp-symlink-outside");
        let outside_file = outside.join("outside.md");
        std::fs::write(&outside_file, "outside original").unwrap();
        symlink_path(&outside_file, &root.join("GRAPH.md.native-tmp"));

        let result = write_workspace_file_impl(root.to_str().unwrap(), "GRAPH.md", "new", None);

        assert_eq!(
            std::fs::read_to_string(&outside_file).unwrap(),
            "outside original",
            "temp symlink write must not overwrite the outside file"
        );
        let error = result.expect_err("pre-existing temp symlink rejected");
        match error {
            WriteWorkspaceError::WriteFailed { message } => assert!(
                message.contains("cannot write temp file"),
                "unexpected error: {message}"
            ),
            WriteWorkspaceError::HashConflict { .. } => panic!("unexpected hash conflict"),
        }
        let _ = std::fs::remove_dir_all(&root);
        let _ = std::fs::remove_dir_all(&outside);
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

    #[cfg(unix)]
    #[test]
    fn read_workspace_file_refuses_symlink_file_escape() {
        let root = temp_root("read-symlink-file-escape");
        let outside = temp_root("read-symlink-file-outside");
        std::fs::write(outside.join("secret.md"), "outside secret").unwrap();
        symlink_path(&outside.join("secret.md"), &root.join("secret.md"));

        let error = read_workspace_file_impl(root.to_str().unwrap(), "secret.md")
            .expect_err("symlink file escape rejected");

        assert!(
            error.contains("escapes workspace"),
            "unexpected error: {error}"
        );
        let _ = std::fs::remove_dir_all(&root);
        let _ = std::fs::remove_dir_all(&outside);
    }

    #[test]
    fn delete_workspace_path_allows_test_input_file_and_golden_baseline_dir_only() {
        let root = temp_root("delete-allowlist");
        std::fs::create_dir_all(root.join(".workspace/test_inputs")).unwrap();
        std::fs::create_dir_all(root.join(".workspace/golden/run-1")).unwrap();
        std::fs::write(root.join(".workspace/test_inputs/case.json"), "{}").unwrap();
        std::fs::write(root.join(".workspace/golden/run-1/result.json"), "{}").unwrap();

        delete_workspace_path_impl(root.to_str().unwrap(), ".workspace/test_inputs/case.json")
            .expect("delete test input file");
        delete_workspace_path_impl(root.to_str().unwrap(), ".workspace/golden/run-1")
            .expect("delete golden baseline dir");

        assert!(!root.join(".workspace/test_inputs/case.json").exists());
        assert!(!root.join(".workspace/golden/run-1").exists());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn delete_workspace_path_refuses_workspace_root_dot() {
        let root = temp_root("delete-dot");

        let error = delete_workspace_path_impl(root.to_str().unwrap(), ".")
            .expect_err("workspace root delete rejected");

        assert!(error.contains("not allowed"), "unexpected error: {error}");
        assert!(root.exists(), "workspace root must survive rejected delete");
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn delete_workspace_path_refuses_arbitrary_dirs_and_files() {
        let root = temp_root("delete-arbitrary");
        std::fs::create_dir_all(root.join(".workspace/test_inputs/nested")).unwrap();
        std::fs::write(root.join(".workspace/test_inputs/nested/child.json"), "{}").unwrap();
        std::fs::write(root.join("GRAPH.md"), "graph").unwrap();

        let dir_error =
            delete_workspace_path_impl(root.to_str().unwrap(), ".workspace/test_inputs/nested")
                .expect_err("arbitrary directory delete rejected");
        let file_error = delete_workspace_path_impl(root.to_str().unwrap(), "GRAPH.md")
            .expect_err("arbitrary file delete rejected");

        assert!(
            dir_error.contains("not allowed"),
            "unexpected dir error: {dir_error}"
        );
        assert!(
            file_error.contains("not allowed"),
            "unexpected file error: {file_error}"
        );
        assert!(root.join(".workspace/test_inputs/nested").exists());
        assert!(root.join("GRAPH.md").exists());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn delete_workspace_path_refuses_traversal() {
        let root = temp_root("delete-traversal");

        assert!(delete_workspace_path_impl(root.to_str().unwrap(), "../escape.json").is_err());
        assert!(delete_workspace_path_impl(root.to_str().unwrap(), "/etc/passwd").is_err());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[cfg(unix)]
    #[test]
    fn delete_workspace_path_refuses_symlink_escape() {
        let root = temp_root("delete-symlink-escape");
        let outside = temp_root("delete-symlink-outside");
        std::fs::write(outside.join("secret.json"), "{}").unwrap();
        symlink_path(&outside.join("secret.json"), &root.join("secret.json"));

        let error = delete_workspace_path_impl(root.to_str().unwrap(), "secret.json")
            .expect_err("non-allowlisted symlink path rejected");

        assert!(error.contains("not allowed"), "unexpected error: {error}");
        assert!(
            outside.join("secret.json").exists(),
            "delete must not remove the outside file"
        );
        let _ = std::fs::remove_dir_all(&root);
        let _ = std::fs::remove_dir_all(&outside);
    }

    #[test]
    fn write_golden_baseline_writes_result_and_metadata() {
        let root = temp_root("golden-write-basic");
        let rs = root.to_str().unwrap();

        write_golden_baseline_impl(
            rs,
            ".workspace/golden/run-1/result.json",
            "{\n  \"ok\": true\n}",
            ".workspace/golden/run-1/golden_metadata.json",
            "{\"id\":\"run-1\"}",
        )
        .expect("golden baseline write");

        assert_eq!(
            std::fs::read_to_string(root.join(".workspace/golden/run-1/result.json")).unwrap(),
            "{\n  \"ok\": true\n}"
        );
        assert_eq!(
            std::fs::read_to_string(root.join(".workspace/golden/run-1/golden_metadata.json"))
                .unwrap(),
            "{\"id\":\"run-1\"}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn write_golden_baseline_rolls_back_new_baseline_when_metadata_publish_fails() {
        let root = temp_root("golden-new-rollback");
        let rs = root.to_str().unwrap();

        let error = write_golden_baseline_impl_for_test(
            rs,
            ".workspace/golden/run-1/result.json",
            "{\"new\":true}",
            ".workspace/golden/run-1/golden_metadata.json",
            "{\"id\":\"run-1\"}",
            true,
        )
        .expect_err("injected metadata publish failure");

        assert!(
            error.contains("injected metadata publish failure"),
            "unexpected error: {error}"
        );
        assert!(
            !root.join(".workspace/golden/run-1").exists(),
            "new baseline dir must not survive a partial publish"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn write_golden_baseline_rolls_back_existing_baseline_when_metadata_publish_fails() {
        let root = temp_root("golden-existing-rollback");
        let baseline = root.join(".workspace/golden/run-1");
        std::fs::create_dir_all(&baseline).unwrap();
        std::fs::write(baseline.join("result.json"), "{\"old\":true}").unwrap();
        std::fs::write(baseline.join("golden_metadata.json"), "{\"id\":\"old\"}").unwrap();
        let rs = root.to_str().unwrap();

        let error = write_golden_baseline_impl_for_test(
            rs,
            ".workspace/golden/run-1/result.json",
            "{\"new\":true}",
            ".workspace/golden/run-1/golden_metadata.json",
            "{\"id\":\"new\"}",
            true,
        )
        .expect_err("injected metadata publish failure");

        assert!(
            error.contains("injected metadata publish failure"),
            "unexpected error: {error}"
        );
        assert_eq!(
            std::fs::read_to_string(baseline.join("result.json")).unwrap(),
            "{\"old\":true}"
        );
        assert_eq!(
            std::fs::read_to_string(baseline.join("golden_metadata.json")).unwrap(),
            "{\"id\":\"old\"}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn write_golden_baseline_rejects_traversal_without_creating_baseline() {
        let root = temp_root("golden-traversal");
        let rs = root.to_str().unwrap();

        assert!(write_golden_baseline_impl(
            rs,
            ".workspace/golden/run-1/result.json",
            "{}",
            ".workspace/golden/../run-1/golden_metadata.json",
            "{}",
        )
        .is_err());
        assert!(!root.join(".workspace/golden/run-1").exists());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[cfg(unix)]
    #[test]
    fn write_golden_baseline_refuses_symlink_escape() {
        let root = temp_root("golden-symlink-escape");
        let outside = temp_root("golden-symlink-outside");
        std::fs::create_dir_all(root.join(".workspace/golden")).unwrap();
        symlink_path(&outside, &root.join(".workspace/golden/run-1"));
        let rs = root.to_str().unwrap();

        let error = write_golden_baseline_impl(
            rs,
            ".workspace/golden/run-1/result.json",
            "{\"new\":true}",
            ".workspace/golden/run-1/golden_metadata.json",
            "{\"id\":\"run-1\"}",
        )
        .expect_err("symlink escape rejected");

        assert!(
            error.contains("escapes workspace"),
            "unexpected error: {error}"
        );
        assert!(
            !outside.join("result.json").exists(),
            "golden writer must not write through an escaping symlink"
        );
        let _ = std::fs::remove_dir_all(&root);
        let _ = std::fs::remove_dir_all(&outside);
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

    #[cfg(unix)]
    #[test]
    fn list_workspace_dir_refuses_symlink_dir_escape() {
        let root = temp_root("list-symlink-dir-escape");
        let outside = temp_root("list-symlink-dir-outside");
        std::fs::write(outside.join("outside.md"), "outside").unwrap();
        symlink_path(&outside, &root.join("link"));

        let error = list_workspace_dir_impl(root.to_str().unwrap(), "link")
            .expect_err("symlink dir escape rejected");

        assert!(
            error.contains("escapes workspace"),
            "unexpected error: {error}"
        );
        let _ = std::fs::remove_dir_all(&root);
        let _ = std::fs::remove_dir_all(&outside);
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

    #[cfg(unix)]
    #[test]
    fn checkpoint_refuses_symlink_file_escape() {
        let root = temp_root("ckpt-read-symlink-file-escape");
        let outside = temp_root("ckpt-read-symlink-file-outside");
        let rs = root.to_str().unwrap();
        std::fs::write(outside.join("secret.md"), "outside secret").unwrap();
        symlink_path(&outside.join("secret.md"), &root.join("secret.md"));

        let error = checkpoint_workspace_file_impl(rs, "secret.md")
            .expect_err("checkpoint target symlink escape rejected");

        assert!(
            error.contains("escapes workspace"),
            "unexpected error: {error}"
        );
        assert!(
            !checkpoint_path(&root, "secret.md").exists(),
            "rejected checkpoint must not create a record"
        );
        let _ = std::fs::remove_dir_all(&root);
        let _ = std::fs::remove_dir_all(&outside);
    }

    #[cfg(unix)]
    #[test]
    fn seed_checkpoint_refuses_symlink_file_escape() {
        let root = temp_root("ckpt-seed-symlink-file-escape");
        let outside = temp_root("ckpt-seed-symlink-file-outside");
        let rs = root.to_str().unwrap();
        std::fs::write(outside.join("secret.md"), "outside secret").unwrap();
        symlink_path(&outside.join("secret.md"), &root.join("secret.md"));

        let error = seed_workspace_checkpoint_impl(rs, "secret.md", "before", true)
            .expect_err("seed target symlink escape rejected");

        assert!(
            error.contains("escapes workspace"),
            "unexpected error: {error}"
        );
        assert!(
            !checkpoint_path(&root, "secret.md").exists(),
            "rejected seed must not create a record"
        );
        let _ = std::fs::remove_dir_all(&root);
        let _ = std::fs::remove_dir_all(&outside);
    }

    #[cfg(unix)]
    #[test]
    fn seed_checkpoint_refuses_existing_record_parent_symlink_escape() {
        let root = temp_root("ckpt-seed-existing-parent-symlink-escape");
        let outside = temp_root("ckpt-seed-existing-parent-symlink-outside");
        let rs = root.to_str().unwrap();
        symlink_path(&outside, &root.join(".gemini"));
        let outside_ckpt = outside
            .join("copilot")
            .join("checkpoints")
            .join(format!("{}.json", sha256_hex("GRAPH.md")));
        std::fs::create_dir_all(outside_ckpt.parent().unwrap()).unwrap();
        let record = CheckpointRecord {
            path: "GRAPH.md".to_string(),
            existed: true,
            content: "outside checkpoint".to_string(),
        };
        std::fs::write(&outside_ckpt, serde_json::to_string(&record).unwrap()).unwrap();

        let error = seed_workspace_checkpoint_impl(rs, "GRAPH.md", "before", true)
            .expect_err("existing checkpoint parent symlink escape rejected");

        assert!(
            error.contains("escapes workspace"),
            "unexpected error: {error}"
        );
        assert!(
            outside_ckpt.exists(),
            "rejected seed must not remove or mutate the outside checkpoint"
        );
        let _ = std::fs::remove_dir_all(&root);
        let _ = std::fs::remove_dir_all(&outside);
    }

    #[cfg(unix)]
    #[test]
    fn restore_existing_file_refuses_symlink_parent_escape() {
        let root = temp_root("ckpt-restore-parent-symlink-escape");
        let outside = temp_root("ckpt-restore-parent-symlink-outside");
        let rs = root.to_str().unwrap();
        std::fs::write(outside.join("owned.md"), "outside current").unwrap();
        symlink_path(&outside, &root.join("link"));

        let record = CheckpointRecord {
            path: "link/owned.md".to_string(),
            existed: true,
            content: "original workspace content".to_string(),
        };
        let ckpt = checkpoint_path(&root, "link/owned.md");
        std::fs::create_dir_all(ckpt.parent().unwrap()).unwrap();
        std::fs::write(&ckpt, serde_json::to_string(&record).unwrap()).unwrap();

        let error = restore_workspace_file_impl(rs, "link/owned.md")
            .expect_err("restore symlink parent escape rejected");

        assert!(
            error.contains("escapes workspace"),
            "unexpected error: {error}"
        );
        assert_eq!(
            std::fs::read_to_string(outside.join("owned.md")).unwrap(),
            "outside current",
            "restore must not write through a symlink parent"
        );
        let _ = std::fs::remove_dir_all(&root);
        let _ = std::fs::remove_dir_all(&outside);
    }

    #[cfg(unix)]
    #[test]
    fn restore_new_file_refuses_symlink_file_escape_before_delete() {
        let root = temp_root("ckpt-restore-delete-symlink-escape");
        let outside = temp_root("ckpt-restore-delete-symlink-outside");
        let rs = root.to_str().unwrap();
        std::fs::write(outside.join("owned.md"), "outside current").unwrap();
        symlink_path(&outside.join("owned.md"), &root.join("new.md"));

        let record = CheckpointRecord {
            path: "new.md".to_string(),
            existed: false,
            content: String::new(),
        };
        let ckpt = checkpoint_path(&root, "new.md");
        std::fs::create_dir_all(ckpt.parent().unwrap()).unwrap();
        std::fs::write(&ckpt, serde_json::to_string(&record).unwrap()).unwrap();

        let error = restore_workspace_file_impl(rs, "new.md")
            .expect_err("restore delete symlink file escape rejected");

        assert!(
            error.contains("escapes workspace"),
            "unexpected error: {error}"
        );
        assert_eq!(
            std::fs::read_to_string(outside.join("owned.md")).unwrap(),
            "outside current",
            "restore delete must not affect the outside file"
        );
        assert!(
            std::fs::symlink_metadata(root.join("new.md")).is_ok(),
            "rejected restore must leave the workspace symlink in place"
        );
        let _ = std::fs::remove_dir_all(&root);
        let _ = std::fs::remove_dir_all(&outside);
    }

    #[cfg(unix)]
    #[test]
    fn clear_checkpoint_refuses_checkpoint_parent_symlink_escape() {
        let root = temp_root("ckpt-clear-parent-symlink-escape");
        let outside = temp_root("ckpt-clear-parent-symlink-outside");
        let rs = root.to_str().unwrap();
        symlink_path(&outside, &root.join(".gemini"));
        let outside_ckpt = checkpoint_path(&outside, "GRAPH.md");
        std::fs::create_dir_all(outside_ckpt.parent().unwrap()).unwrap();
        std::fs::write(&outside_ckpt, "{}").unwrap();

        let error = clear_workspace_checkpoint_impl(rs, "GRAPH.md")
            .expect_err("clear checkpoint symlink parent escape rejected");

        assert!(
            error.contains("escapes workspace"),
            "unexpected error: {error}"
        );
        assert!(
            outside_ckpt.exists(),
            "clear must not delete checkpoint through a symlink parent"
        );
        let _ = std::fs::remove_dir_all(&root);
        let _ = std::fs::remove_dir_all(&outside);
    }

    #[cfg(unix)]
    #[test]
    fn checkpoint_refuses_preexisting_temp_symlink_escape() {
        let root = temp_root("ckpt-temp-symlink-escape");
        let outside = temp_root("ckpt-temp-symlink-outside");
        let rs = root.to_str().unwrap();
        std::fs::write(root.join("GRAPH.md"), "checkpoint me").unwrap();
        let outside_file = outside.join("outside.json");
        std::fs::write(&outside_file, "outside original").unwrap();

        let ckpt = checkpoint_path(&root, "GRAPH.md");
        std::fs::create_dir_all(ckpt.parent().unwrap()).unwrap();
        let mut temp_os = ckpt.clone().into_os_string();
        temp_os.push(".native-tmp");
        symlink_path(&outside_file, &PathBuf::from(temp_os));

        let result = checkpoint_workspace_file_impl(rs, "GRAPH.md");

        assert_eq!(
            std::fs::read_to_string(&outside_file).unwrap(),
            "outside original",
            "checkpoint temp symlink write must not overwrite the outside file"
        );
        let error = result.expect_err("pre-existing checkpoint temp symlink rejected");
        assert!(
            error.contains("cannot write temp file"),
            "unexpected error: {error}"
        );
        let _ = std::fs::remove_dir_all(&root);
        let _ = std::fs::remove_dir_all(&outside);
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

    // ── New-skill / Open-folder native-fs ───────────────────────────────────

    fn git_available() -> bool {
        std::process::Command::new("git")
            .arg("--version")
            .output()
            .map(|output| output.status.success())
            .unwrap_or(false)
    }

    #[test]
    fn create_skill_workspace_writes_scaffold_workspace_gitignore_and_git_repo() {
        if !git_available() {
            eprintln!("skipping: git not available");
            return;
        }
        let config = temp_root("create-full");
        let parent = config.join("Skills");
        std::fs::create_dir_all(&parent).unwrap();

        let outcome = create_skill_workspace_impl("", "demo-skill", &config)
            .expect("create skill workspace");
        let root = PathBuf::from(&outcome.root);

        assert_eq!(outcome.skill_id, "demo-skill");
        assert_eq!(root, parent.join("demo-skill"));

        // Scaffold files, byte-for-byte to Python _SCAFFOLD_FILES with name substituted.
        let graph = std::fs::read_to_string(root.join("GRAPH.md")).unwrap();
        assert!(graph.contains("name: demo-skill"), "GRAPH.md name substituted");
        assert!(graph.contains("schema_version: \"v0.3.0\""));
        assert!(graph.trim_end().ends_with("<phase depends_on=\"input\" output>init</phase>"));
        assert!(root.join("phases/init/LOGIC.md").is_file());
        let initialize = std::fs::read_to_string(root.join("phases/init/actions/initialize.py")).unwrap();
        assert!(initialize.contains("def initialize(context):"));

        // .workspace dir and .gitignore.
        assert!(root.join(".workspace").is_dir());
        assert_eq!(
            std::fs::read_to_string(root.join(".gitignore")).unwrap(),
            "/.workspace/*\n!/.workspace/golden/\n/.workspace/local_settings.json\n"
        );

        // Git repo exists with the "initial-skill" commit.
        assert!(root.join(".git").is_dir(), "git repo initialized");
        let log = std::process::Command::new("git")
            .args(["log", "--oneline"])
            .current_dir(&root)
            .output()
            .expect("git log");
        let log_text = String::from_utf8_lossy(&log.stdout);
        assert!(log_text.contains("initial-skill"), "initial-skill commit present: {log_text}");

        let _ = std::fs::remove_dir_all(&config);
    }

    #[test]
    fn create_skill_workspace_writes_byte_for_byte_skill_index_entry() {
        if !git_available() {
            eprintln!("skipping: git not available");
            return;
        }
        let config = temp_root("create-index");
        std::fs::create_dir_all(config.join("Skills")).unwrap();

        let outcome = create_skill_workspace_impl("", "alpha", &config).expect("create");
        let index_raw = std::fs::read_to_string(config.join("skill_index.json")).unwrap();
        // Python `_write_skill_index`: sorted keys, 2-space indent, trailing newline.
        let expected = format!(
            "{{\n  \"alpha\": {{\n    \"absolute_path\": \"{}\",\n    \"l2_remote_url\": \"\"\n  }}\n}}\n",
            outcome.root
        );
        assert_eq!(index_raw, expected, "skill_index.json byte shape must match Python");
        let _ = std::fs::remove_dir_all(&config);
    }

    #[test]
    fn create_skill_workspace_upsert_preserves_sorted_existing_entries() {
        if !git_available() {
            eprintln!("skipping: git not available");
            return;
        }
        let config = temp_root("create-index-upsert");
        std::fs::create_dir_all(&config).unwrap();
        // Pre-seed an existing entry that should survive and stay sorted before "beta".
        std::fs::write(
            config.join("skill_index.json"),
            "{\n  \"zeta\": {\n    \"absolute_path\": \"/existing/zeta\",\n    \"l2_remote_url\": \"\"\n  }\n}\n",
        )
        .unwrap();
        std::fs::create_dir_all(config.join("Skills")).unwrap();

        let outcome = create_skill_workspace_impl("", "beta", &config).expect("create");
        let index_raw = std::fs::read_to_string(config.join("skill_index.json")).unwrap();
        let expected = format!(
            "{{\n  \"beta\": {{\n    \"absolute_path\": \"{}\",\n    \"l2_remote_url\": \"\"\n  }},\n  \"zeta\": {{\n    \"absolute_path\": \"/existing/zeta\",\n    \"l2_remote_url\": \"\"\n  }}\n}}\n",
            outcome.root
        );
        assert_eq!(index_raw, expected, "upsert keeps sorted keys + existing entry");
        let _ = std::fs::remove_dir_all(&config);
    }

    #[test]
    fn create_skill_workspace_rejects_non_empty_target_dir() {
        let config = temp_root("create-nonempty");
        let parent = config.join("Skills");
        let target = parent.join("taken");
        std::fs::create_dir_all(&target).unwrap();
        std::fs::write(target.join("existing.txt"), "occupied").unwrap();

        let error = create_skill_workspace_impl(parent.to_str().unwrap(), "taken", &config)
            .expect_err("non-empty target rejected");
        assert!(error.contains("non-empty"), "unexpected error: {error}");
        // The pre-existing file must be untouched.
        assert_eq!(std::fs::read_to_string(target.join("existing.txt")).unwrap(), "occupied");
        let _ = std::fs::remove_dir_all(&config);
    }

    #[test]
    fn create_skill_workspace_rejects_invalid_skill_id() {
        let config = temp_root("create-badid");
        std::fs::create_dir_all(config.join("Skills")).unwrap();
        for bad in ["", "..", "a/b", "a\\b", "-leading", "."] {
            assert!(
                create_skill_workspace_impl("", bad, &config).is_err(),
                "expected rejection for id {bad:?}"
            );
        }
        let _ = std::fs::remove_dir_all(&config);
    }

    #[test]
    fn create_skill_workspace_rejects_missing_explicit_parent() {
        let config = temp_root("create-noparent");
        let missing = config.join("nope").join("here");
        let error = create_skill_workspace_impl(missing.to_str().unwrap(), "x", &config)
            .expect_err("missing parent rejected");
        assert!(error.contains("parent directory does not exist"), "unexpected: {error}");
        let _ = std::fs::remove_dir_all(&config);
    }

    #[test]
    fn create_skill_workspace_defaults_parent_to_config_skills() {
        if !git_available() {
            eprintln!("skipping: git not available");
            return;
        }
        let config = temp_root("create-default-parent");
        std::fs::create_dir_all(config.join("Skills")).unwrap();
        let outcome = create_skill_workspace_impl("   ", "gamma", &config).expect("create default");
        assert_eq!(PathBuf::from(&outcome.root), config.join("Skills").join("gamma"));
        let _ = std::fs::remove_dir_all(&config);
    }

    #[test]
    fn create_skill_workspace_honors_app_settings_default_skills_directory() {
        if !git_available() {
            eprintln!("skipping: git not available");
            return;
        }
        let config = temp_root("create-settings-default");
        let custom = temp_root("create-settings-target");
        std::fs::create_dir_all(&config).unwrap();
        std::fs::write(
            config.join("app_settings.json"),
            format!("{{\n  \"default_skills_directory\": \"{}\"\n}}\n", custom.display()),
        )
        .unwrap();

        let outcome = create_skill_workspace_impl("", "delta", &config).expect("create");
        assert_eq!(PathBuf::from(&outcome.root), custom.join("delta"));
        let _ = std::fs::remove_dir_all(&config);
        let _ = std::fs::remove_dir_all(&custom);
    }

    #[test]
    fn create_skill_workspace_uses_app_settings_user_id_for_git_author() {
        if !git_available() {
            eprintln!("skipping: git not available");
            return;
        }
        let config = temp_root("create-gitauthor");
        std::fs::create_dir_all(config.join("Skills")).unwrap();
        std::fs::write(
            config.join("app_settings.json"),
            "{\n  \"user_id\": \"alice\"\n}\n",
        )
        .unwrap();

        let outcome = create_skill_workspace_impl("", "epsilon", &config).expect("create");
        let root = PathBuf::from(&outcome.root);
        let name = std::process::Command::new("git")
            .args(["config", "--local", "user.name"])
            .current_dir(&root)
            .output()
            .unwrap();
        let email = std::process::Command::new("git")
            .args(["config", "--local", "user.email"])
            .current_dir(&root)
            .output()
            .unwrap();
        assert_eq!(String::from_utf8_lossy(&name.stdout).trim(), "alice");
        assert_eq!(String::from_utf8_lossy(&email.stdout).trim(), "alice@studio.local");
        let _ = std::fs::remove_dir_all(&config);
    }

    #[test]
    fn open_skill_workspace_returns_root_for_dir_without_graph_md() {
        let config = temp_root("open-no-graph");
        let folder = temp_root("open-folder-bare");
        // A bare folder with no GRAPH.md must still open (D2: no manifest check).
        std::fs::create_dir_all(&folder).unwrap();
        std::fs::create_dir_all(&config).unwrap();

        let outcome = open_skill_workspace_impl(folder.to_str().unwrap(), &config)
            .expect("open bare folder");
        assert_eq!(PathBuf::from(&outcome.root), folder);
        // skill_id derived from the folder name via the TS-parity port.
        assert_eq!(outcome.skill_id, skill_id_from_workspace_root(folder.to_str().unwrap()));
        // The index entry is written so the detail GET can resolve id→dir.
        let index_raw = std::fs::read_to_string(config.join("skill_index.json")).unwrap();
        assert!(index_raw.contains(&outcome.skill_id));
        assert!(index_raw.contains(&outcome.root));
        let _ = std::fs::remove_dir_all(&config);
        let _ = std::fs::remove_dir_all(&folder);
    }

    #[test]
    fn open_skill_workspace_rejects_missing_or_file_path() {
        let config = temp_root("open-bad");
        let missing = config.join("ghost");
        let file = config.join("a-file");
        std::fs::create_dir_all(&config).unwrap();
        std::fs::write(&file, "i am a file").unwrap();

        assert!(open_skill_workspace_impl(missing.to_str().unwrap(), &config).is_err());
        let file_error = open_skill_workspace_impl(file.to_str().unwrap(), &config)
            .expect_err("file path rejected");
        assert!(file_error.contains("not a directory"), "unexpected: {file_error}");
        assert!(open_skill_workspace_impl("  ", &config).is_err());
        let _ = std::fs::remove_dir_all(&config);
    }

    #[test]
    fn workspace_path_exists_reports_true_and_false() {
        let root = temp_root("exists-check");
        assert!(workspace_path_exists_impl(root.to_str().unwrap()));
        assert!(!workspace_path_exists_impl(&root.join("missing").to_string_lossy()));
        assert!(!workspace_path_exists_impl("   "));
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn skill_id_from_workspace_root_matches_frontend_derivation() {
        // Parity with frontend `skillIdFromWorkspaceRoot`
        // (components/studio/workspace-identity.ts). Expected values computed by
        // hand from that function's spec; any drift breaks the registry-free
        // token↔index key handoff.
        let cases = [
            ("/Users/me/My Skill", "my-skill"),
            ("/Users/me/Already-Good", "already-good"),
            ("/Users/me/123start", "skill-123start"),
            ("/Users/me/  spaced  ", "spaced"),
            ("/Users/me/weird__name!!", "weird-name"),
            ("/Users/me/trailing/", "trailing"),
            ("/Users/me/UPPER", "upper"),
            ("/Users/me/9", "skill-9"),
            ("C:\\Users\\me\\Win Skill", "win-skill"),
        ];
        for (path, expected) in cases {
            assert_eq!(
                skill_id_from_workspace_root(path),
                expected,
                "skill_id parity for {path:?}"
            );
        }
    }
}
