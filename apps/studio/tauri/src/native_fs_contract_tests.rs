use std::fs;
use std::path::{Path, PathBuf};

use crate::{
    add_recent_workspace, ensure_workspace_support_dirs, list_recent_workspaces,
    remove_recent_workspace, write_workspace_file, NativeFsError, RecentWorkspace,
    WriteWorkspaceFileRequest,
};

fn temp_dir(name: &str) -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "skill-studio-native-fs-{name}-{}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&path);
    fs::create_dir_all(&path).expect("create temp dir");
    path
}

fn cleanup(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

#[test]
fn writer_creates_workspace_files_and_rejects_stale_expected_hashes() {
    let workspace = temp_dir("writer-conflict");
    let request = WriteWorkspaceFileRequest {
        workspace_root: workspace.clone(),
        relative_path: "phases/init/LOGIC.md".to_string(),
        content: "first version\n".to_string(),
        expected_hash: None,
    };

    let first = write_workspace_file(request).expect("initial write succeeds");
    assert_eq!(
        fs::read_to_string(workspace.join("phases/init/LOGIC.md")).expect("read written file"),
        "first version\n",
    );

    let stale = write_workspace_file(WriteWorkspaceFileRequest {
        workspace_root: workspace.clone(),
        relative_path: "phases/init/LOGIC.md".to_string(),
        content: "second version\n".to_string(),
        expected_hash: Some("stale-hash".to_string()),
    })
    .expect_err("stale expected hash should conflict");

    match stale {
        NativeFsError::HashConflict {
            current_hash,
            current_content,
        } => {
            assert_eq!(current_hash, first.hash);
            assert_eq!(current_content, "first version\n");
        }
        other => panic!("expected HashConflict, got {other:?}"),
    }
    assert_eq!(
        fs::read_to_string(workspace.join("phases/init/LOGIC.md")).expect("read protected file"),
        "first version\n",
    );
    cleanup(&workspace);
}

#[test]
fn writer_rejects_empty_absolute_and_workspace_escaping_paths() {
    let workspace = temp_dir("path-guard");
    for relative_path in ["", "/tmp/outside.md", "../outside.md", "phases/../outside.md"] {
        let error = write_workspace_file(WriteWorkspaceFileRequest {
            workspace_root: workspace.clone(),
            relative_path: relative_path.to_string(),
            content: "escape\n".to_string(),
            expected_hash: None,
        })
        .expect_err("invalid path should fail loud");
        assert!(
            matches!(error, NativeFsError::InvalidPath { .. }),
            "expected InvalidPath for {relative_path:?}, got {error:?}",
        );
    }
    assert!(!workspace.parent().unwrap().join("outside.md").exists());
    cleanup(&workspace);
}

#[test]
fn workspace_support_dirs_are_created_under_dot_workspace() {
    let workspace = temp_dir("workspace-dirs");

    let dirs = ensure_workspace_support_dirs(&workspace).expect("create support dirs");

    assert_eq!(dirs.workspace_dir, workspace.join(".workspace"));
    for expected in ["runs", "golden", "artifacts", "test_inputs"] {
        assert!(workspace.join(".workspace").join(expected).is_dir());
    }
    cleanup(&workspace);
}

#[test]
fn recent_workspaces_are_path_based_persistent_and_removable_without_deleting_disk() {
    let config_dir = temp_dir("mru-config");
    let workspace = temp_dir("mru-workspace");
    let other_workspace = temp_dir("mru-other-workspace");

    add_recent_workspace(
        &config_dir,
        RecentWorkspace {
            absolute_path: workspace.clone(),
            display_name: "mru-workspace".to_string(),
            identity: format!("local:{}", workspace.display()),
            last_opened_at: "2026-06-06T12:00:00Z".to_string(),
        },
    )
    .expect("add first recent workspace");
    add_recent_workspace(
        &config_dir,
        RecentWorkspace {
            absolute_path: other_workspace.clone(),
            display_name: "mru-other-workspace".to_string(),
            identity: format!("local:{}", other_workspace.display()),
            last_opened_at: "2026-06-06T12:01:00Z".to_string(),
        },
    )
    .expect("add second recent workspace");

    let listed = list_recent_workspaces(&config_dir).expect("list recent workspaces");
    assert_eq!(
        listed
            .iter()
            .map(|workspace| workspace.absolute_path.as_path())
            .collect::<Vec<_>>(),
        vec![other_workspace.as_path(), workspace.as_path()],
    );

    remove_recent_workspace(&config_dir, &format!("local:{}", workspace.display()))
        .expect("remove recent workspace");

    let listed = list_recent_workspaces(&config_dir).expect("list after remove");
    assert_eq!(listed.len(), 1);
    assert_eq!(listed[0].absolute_path, other_workspace);
    assert!(workspace.exists(), "Remove from Studio must not delete the workspace folder");

    cleanup(&workspace);
    cleanup(&other_workspace);
    cleanup(&config_dir);
}
