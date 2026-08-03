//! Embedded CLI terminal host (design: `docs/studio/mvp1/03_regions/copilot/
//! ah-orchestration-design.md` §10, "CLI 即 copilot").
//!
//! The desktop shell owns the CLI session's process: it runs the very same
//! launcher script the external-terminal path used to hand to a console window,
//! but inside a pseudo terminal it controls, and relays the byte stream to the
//! Copilot panel. The frontend renders and forwards keystrokes; it never learns
//! how a session is started.
//!
//! Output travels over a Tauri **channel**, not the global event bus: the
//! channel is created by the panel and handed to the launch command, so the
//! delivery path exists before the process does. That ordering is not a detail
//! — Windows' ConPTY opens by asking the terminal where the cursor is and stays
//! silent until it is answered, so a transport that can lose the first bytes
//! (a broadcast the receiver has to filter by an id it does not have yet)
//! deadlocks the session. Channels are also what Tauri itself streams child
//! process output over.
//!
//! Bytes cross the bridge base64-encoded because a PTY read can split a
//! multi-byte UTF-8 sequence: decoding per chunk would corrupt it, so the raw
//! bytes travel intact and the terminal emulator does the decoding.

use std::collections::HashMap;
use std::io::{Read, Write};
use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

use base64::Engine as _;
use base64::engine::general_purpose::STANDARD as BASE64;
use portable_pty::{CommandBuilder, MasterPty, PtySize, native_pty_system};
use serde::Serialize;
use tauri::ipc::Channel;

/// A PTY read buffer sized to one screenful of dense output; larger reads just
/// mean fewer events, smaller ones mean choppier rendering.
const READ_CHUNK_BYTES: usize = 8 * 1024;

/// What the panel's terminal receives over its channel.
#[derive(Clone, Serialize)]
#[serde(tag = "event", rename_all = "camelCase")]
pub enum CliTerminalEvent {
    /// base64 of the raw PTY bytes (see module docs).
    Output { chunk: String },
    Exit { code: Option<i32> },
}

/// How one CLI session is launched inside the PTY.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LauncherCommand {
    pub program: String,
    pub args: Vec<String>,
}

struct Session {
    /// Workspace + assistant this session belongs to. One owner may only have
    /// one live session; starting a new one ends the old.
    owner: String,
    writer: Box<dyn Write + Send>,
    master: Box<dyn MasterPty + Send>,
    child: Arc<Mutex<Box<dyn portable_pty::Child + Send + Sync>>>,
}

/// Session ids must be unique per START, not per owner: a view that mounts,
/// unmounts and remounts (React does exactly this in development) would
/// otherwise have the first mount's teardown kill the second mount's live
/// session, because both computed the same id.
static NEXT_SESSION_SEQUENCE: AtomicU64 = AtomicU64::new(1);

fn next_session_id(owner: &str) -> String {
    format!(
        "{owner}-{}",
        NEXT_SESSION_SEQUENCE.fetch_add(1, Ordering::Relaxed)
    )
}

/// Live PTY sessions, keyed by the session id handed to the frontend.
#[derive(Default)]
pub struct CliTerminalState {
    sessions: Mutex<HashMap<String, Session>>,
}

impl CliTerminalState {
    fn lock(&self) -> std::sync::MutexGuard<'_, HashMap<String, Session>> {
        self.sessions
            .lock()
            .expect("cli terminal sessions poisoned")
    }
}

/// Terminal size to start a session at, before the panel reports its measured
/// grid. tmux redraws on the first resize, so this only shapes the first frame.
pub fn initial_size(cols: u16, rows: u16) -> PtySize {
    PtySize {
        rows: rows.max(4),
        cols: cols.max(20),
        pixel_width: 0,
        pixel_height: 0,
    }
}

/// Start `command` in a PTY and stream its output to the frontend. Returns the
/// new session's id. Any session the same owner already had is ended first —
/// one workspace + assistant pair has exactly one live terminal client.
pub fn spawn(
    on_event: Channel<CliTerminalEvent>,
    state: &CliTerminalState,
    owner: &str,
    command: &LauncherCommand,
    cwd: &Path,
    size: PtySize,
) -> Result<String, String> {
    close_owner(state, owner);
    let session_id = next_session_id(owner);

    let PtyProcess {
        reader,
        writer,
        master,
        child,
    } = open_pty(command, cwd, size)?;
    let child = Arc::new(Mutex::new(child));
    state.lock().insert(
        session_id.clone(),
        Session {
            owner: owner.to_string(),
            writer,
            master,
            child: Arc::clone(&child),
        },
    );

    spawn_reader_thread(on_event, reader, child);
    Ok(session_id)
}

/// A running command and the pseudo-terminal ends the host holds onto.
struct PtyProcess {
    reader: Box<dyn Read + Send>,
    writer: Box<dyn Write + Send>,
    master: Box<dyn MasterPty + Send>,
    child: Box<dyn portable_pty::Child + Send + Sync>,
}

/// Start `command` under a pseudo terminal. Split out from `spawn` so the byte
/// path (start → read → write → resize) is testable without a Tauri app.
fn open_pty(
    command: &LauncherCommand,
    cwd: &Path,
    size: PtySize,
) -> Result<PtyProcess, String> {
    let pair = native_pty_system()
        .openpty(size)
        .map_err(|error| format!("failed to open a terminal for the CLI session: {error}"))?;

    let mut builder = CommandBuilder::new(&command.program);
    for arg in &command.args {
        builder.arg(arg);
    }
    builder.cwd(cwd);
    // TUIs (tmux, the CLI's own renderer) pick their capabilities from TERM;
    // without it they fall back to a dumb terminal and draw nothing usable.
    builder.env("TERM", "xterm-256color");

    let child = pair
        .slave
        .spawn_command(builder)
        .map_err(|error| format!("failed to start {}: {error}", command.program))?;
    // The slave handle must go away for the child's exit to close the master's
    // read side; holding it would make the reader loop hang forever.
    drop(pair.slave);

    let reader = pair
        .master
        .try_clone_reader()
        .map_err(|error| format!("failed to read from the CLI session: {error}"))?;
    let writer = pair
        .master
        .take_writer()
        .map_err(|error| format!("failed to write to the CLI session: {error}"))?;

    Ok(PtyProcess {
        reader,
        writer,
        master: pair.master,
        child,
    })
}

fn spawn_reader_thread(
    on_event: Channel<CliTerminalEvent>,
    mut reader: Box<dyn Read + Send>,
    child: Arc<Mutex<Box<dyn portable_pty::Child + Send + Sync>>>,
) {
    std::thread::spawn(move || {
        let mut buffer = vec![0u8; READ_CHUNK_BYTES];
        loop {
            match reader.read(&mut buffer) {
                Ok(0) | Err(_) => break,
                Ok(read) => {
                    let chunk = BASE64.encode(&buffer[..read]);
                    // A closed channel means the panel dropped this terminal;
                    // stop pumping instead of spinning on a dead receiver.
                    if let Err(error) = on_event.send(CliTerminalEvent::Output { chunk }) {
                        log::warn!("phase=cli-terminal action=send-failed error={error}");
                        break;
                    }
                }
            }
        }

        let code = child
            .lock()
            .ok()
            .and_then(|mut child| child.wait().ok())
            .map(|status| status.exit_code() as i32);
        let _ = on_event.send(CliTerminalEvent::Exit { code });
    });
}

pub fn write(state: &CliTerminalState, session_id: &str, data: &str) -> Result<(), String> {
    let mut sessions = state.lock();
    let session = sessions
        .get_mut(session_id)
        .ok_or_else(|| format!("no live CLI terminal for session {session_id}"))?;
    session
        .writer
        .write_all(data.as_bytes())
        .and_then(|()| session.writer.flush())
        .map_err(|error| format!("failed to send input to the CLI session: {error}"))
}

pub fn resize(
    state: &CliTerminalState,
    session_id: &str,
    cols: u16,
    rows: u16,
) -> Result<(), String> {
    let sessions = state.lock();
    let session = sessions
        .get(session_id)
        .ok_or_else(|| format!("no live CLI terminal for session {session_id}"))?;
    session
        .master
        .resize(initial_size(cols, rows))
        .map_err(|error| format!("failed to resize the CLI session: {error}"))
}

/// Terminate the local terminal client. Per the design's detach semantics this
/// does NOT end the ah runtime: killing a tmux client leaves the session (and
/// every agent inside it) running under the daemon.
pub fn close(state: &CliTerminalState, session_id: &str) -> bool {
    let Some(session) = state.lock().remove(session_id) else {
        return false;
    };
    if let Ok(mut child) = session.child.lock() {
        let _ = child.kill();
        let _ = child.wait();
    }
    true
}

/// Ends whatever session this workspace + assistant pair currently has.
pub fn close_owner(state: &CliTerminalState, owner: &str) {
    let ids = state
        .lock()
        .iter()
        .filter(|(_, session)| session.owner == owner)
        .map(|(id, _)| id.clone())
        .collect::<Vec<_>>();
    for id in ids {
        close(state, &id);
    }
}

pub fn close_all(state: &CliTerminalState) {
    let ids = state.lock().keys().cloned().collect::<Vec<_>>();
    for id in ids {
        close(state, &id);
    }
}


#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn initial_size_clamps_degenerate_grids() {
        // A panel measured mid-animation can report a 0x0 grid; a PTY sized
        // that way makes tmux draw nothing at all.
        let size = initial_size(0, 0);
        assert_eq!(size.cols, 20);
        assert_eq!(size.rows, 4);

        let measured = initial_size(120, 30);
        assert_eq!(measured.cols, 120);
        assert_eq!(measured.rows, 30);
    }

    /// Windows' ConPTY opens by asking the terminal where the cursor is
    /// (`ESC [ 6 n`) and emits nothing further until it gets an answer. A real
    /// emulator replies on its own; this test has to play that part, which is
    /// exactly why the frontend must never drop bytes that arrive before it
    /// knows the session id (see `classifyCliTerminalOutput`).
    fn answer_cursor_position_query(chunk: &str, writer: &mut Box<dyn Write + Send>) {
        if chunk.contains("\x1b[6n") {
            let _ = writer.write_all(b"\x1b[1;1R");
            let _ = writer.flush();
        }
    }

    #[test]
    fn pty_delivers_the_child_process_output() {
        // The whole feature rests on this: a command started under the PTY must
        // stream its bytes back through the reader we hand the event pump.
        let command = if cfg!(target_os = "windows") {
            LauncherCommand {
                program: "cmd.exe".to_string(),
                args: vec!["/c".to_string(), "echo studio-pty-probe".to_string()],
            }
        } else {
            LauncherCommand {
                program: "/bin/sh".to_string(),
                args: vec!["-c".to_string(), "echo studio-pty-probe".to_string()],
            }
        };

        let mut process = open_pty(&command, &std::env::temp_dir(), initial_size(80, 24))
            .expect("PTY must start the probe command");

        let mut seen = String::new();
        let mut buffer = [0u8; 4096];
        for _ in 0..200 {
            match process.reader.read(&mut buffer) {
                Ok(0) | Err(_) => break,
                Ok(read) => {
                    let chunk = String::from_utf8_lossy(&buffer[..read]).to_string();
                    answer_cursor_position_query(&chunk, &mut process.writer);
                    seen.push_str(&chunk);
                    if seen.contains("studio-pty-probe") {
                        break;
                    }
                }
            }
        }
        let _ = process.child.kill();

        assert!(
            seen.contains("studio-pty-probe"),
            "PTY produced no output; got: {seen:?}"
        );
    }

    #[test]
    fn write_and_resize_reject_unknown_sessions() {
        let state = CliTerminalState::default();

        assert!(write(&state, "claude-abc", "ls\n").is_err());
        assert!(resize(&state, "claude-abc", 80, 24).is_err());
        assert!(!close(&state, "claude-abc"));
    }
}
