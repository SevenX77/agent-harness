use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WriteWorkspaceFileRequest {
    pub workspace_root: PathBuf,
    pub relative_path: String,
    pub content: String,
    pub expected_hash: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WriteWorkspaceFileResponse {
    pub path: String,
    pub relative_path: String,
    pub hash: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkspaceSupportDirs {
    pub workspace_dir: PathBuf,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RecentWorkspace {
    pub absolute_path: PathBuf,
    pub display_name: String,
    pub identity: String,
    pub last_opened_at: String,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(tag = "type", content = "data")]
pub enum NativeFsError {
    HashConflict {
        current_hash: String,
        current_content: String,
    },
    InvalidPath {
        path: String,
        message: String,
    },
    Io {
        message: String,
    },
}

impl std::fmt::Display for NativeFsError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::HashConflict { current_hash, .. } => {
                write!(f, "Hash conflict with hash {}", current_hash)
            }
            Self::InvalidPath { path, message } => {
                write!(f, "Invalid path {}: {}", path, message)
            }
            Self::Io { message } => {
                write!(f, "IO error: {}", message)
            }
        }
    }
}

impl std::error::Error for NativeFsError {}

fn sha256_hex(content: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(content.as_bytes());
    format!("{:x}", hasher.finalize())
}

fn validate_and_canonicalize_path(
    workspace_root: &Path,
    relative_path: &str,
) -> Result<PathBuf, NativeFsError> {
    if relative_path.trim().is_empty() {
        return Err(NativeFsError::InvalidPath {
            path: relative_path.to_string(),
            message: "Path cannot be empty".to_string(),
        });
    }

    let rel_path_buf = PathBuf::from(relative_path);
    if rel_path_buf.is_absolute() {
        return Err(NativeFsError::InvalidPath {
            path: relative_path.to_string(),
            message: "Absolute path is not allowed inside workspace".to_string(),
        });
    }

    if relative_path.contains("..") {
        return Err(NativeFsError::InvalidPath {
            path: relative_path.to_string(),
            message: "Path traversal is not allowed".to_string(),
        });
    }

    let canonical_root = workspace_root.canonicalize().map_err(|e| {
        NativeFsError::InvalidPath {
            path: workspace_root.display().to_string(),
            message: format!("Workspace root canonicalization failed: {}", e),
        }
    })?;

    let joined = canonical_root.join(&rel_path_buf);

    if !joined.starts_with(&canonical_root) {
        return Err(NativeFsError::InvalidPath {
            path: relative_path.to_string(),
            message: "Path escapes the workspace root".to_string(),
        });
    }

    Ok(workspace_root.join(rel_path_buf))
}

pub fn write_workspace_file(
    req: WriteWorkspaceFileRequest,
) -> Result<WriteWorkspaceFileResponse, NativeFsError> {
    let target_path = validate_and_canonicalize_path(&req.workspace_root, &req.relative_path)?;

    if target_path.exists() {
        let current_content = std::fs::read_to_string(&target_path).map_err(|e| {
            NativeFsError::Io {
                message: format!("Failed to read existing file: {}", e),
            }
        })?;
        let current_hash = sha256_hex(&current_content);

        if let Some(expected) = &req.expected_hash {
            if current_hash != *expected {
                return Err(NativeFsError::HashConflict {
                    current_hash,
                    current_content,
                });
            }
        }
    } else if req.expected_hash.is_some() {
        return Err(NativeFsError::HashConflict {
            current_hash: "".to_string(),
            current_content: "".to_string(),
        });
    }

    if let Some(parent) = target_path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| {
            NativeFsError::Io {
                message: format!("Failed to create parent directories: {}", e),
            }
        })?;
    }

    std::fs::write(&target_path, &req.content).map_err(|e| {
        NativeFsError::Io {
            message: format!("Failed to write file: {}", e),
        }
    })?;

    let hash = sha256_hex(&req.content);

    Ok(WriteWorkspaceFileResponse {
        path: req.relative_path.clone(),
        relative_path: req.relative_path,
        hash,
    })
}

pub fn ensure_workspace_support_dirs(
    workspace_root: &Path,
) -> Result<WorkspaceSupportDirs, NativeFsError> {
    let workspace_dir = workspace_root.join(".workspace");
    std::fs::create_dir_all(&workspace_dir).map_err(|e| {
        NativeFsError::Io {
            message: format!("Failed to create .workspace directory: {}", e),
        }
    })?;

    for subdir in &["runs", "golden", "artifacts", "test_inputs"] {
        std::fs::create_dir_all(workspace_dir.join(subdir)).map_err(|e| {
            NativeFsError::Io {
                message: format!("Failed to create support directory .workspace/{}: {}", subdir, e),
            }
        })?;
    }

    Ok(WorkspaceSupportDirs { workspace_dir })
}

pub fn add_recent_workspace(
    config_dir: &Path,
    workspace: RecentWorkspace,
) -> Result<(), NativeFsError> {
    let mru_file = config_dir.join("recent_workspaces.json");
    if !config_dir.exists() {
        std::fs::create_dir_all(config_dir).map_err(|e| {
            NativeFsError::Io {
                message: format!("Failed to create config dir: {}", e),
            }
        })?;
    }

    let mut list = list_recent_workspaces(config_dir)?;

    list.retain(|w| w.identity != workspace.identity && w.absolute_path != workspace.absolute_path);
    list.insert(0, workspace);
    list.truncate(10);

    let content = serde_json::to_string(&list).map_err(|e| {
        NativeFsError::Io {
            message: format!("Failed to serialize recent workspaces: {}", e),
        }
    })?;

    std::fs::write(mru_file, content).map_err(|e| {
        NativeFsError::Io {
            message: format!("Failed to write recent workspaces file: {}", e),
        }
    })?;

    Ok(())
}

pub fn list_recent_workspaces(config_dir: &Path) -> Result<Vec<RecentWorkspace>, NativeFsError> {
    let mru_file = config_dir.join("recent_workspaces.json");
    if !mru_file.exists() {
        return Ok(Vec::new());
    }

    let content = std::fs::read_to_string(mru_file).map_err(|e| {
        NativeFsError::Io {
            message: format!("Failed to read recent workspaces: {}", e),
        }
    })?;

    let list: Vec<RecentWorkspace> = serde_json::from_str(&content).map_err(|e| {
        NativeFsError::Io {
            message: format!("Failed to parse recent workspaces: {}", e),
        }
    })?;

    Ok(list)
}

pub fn remove_recent_workspace(config_dir: &Path, identity: &str) -> Result<(), NativeFsError> {
    let mru_file = config_dir.join("recent_workspaces.json");
    let mut list = list_recent_workspaces(config_dir)?;

    list.retain(|w| w.identity != identity);

    let content = serde_json::to_string(&list).map_err(|e| {
        NativeFsError::Io {
            message: format!("Failed to serialize recent workspaces: {}", e),
        }
    })?;

    std::fs::write(mru_file, content).map_err(|e| {
        NativeFsError::Io {
            message: format!("Failed to write recent workspaces file: {}", e),
        }
    })?;

    Ok(())
}
