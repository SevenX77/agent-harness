---
spec: studio-ah-state-contract-v1
doc: upstream-issues-draft
date: 2026-07-10
purpose: "Draft text for two ah upstream issues identified during operator review (F1, F4b/F8). Operator files these on github.com/SevenX77/ah — this file is not submitted automatically."
status: draft, not filed
---

# Upstream `ah` issues (draft)

Both issues below are written from evidence recorded in `operator-review-findings.md` (F1, F4b, F8) and cross-checked in `research.md`'s 2026-07-10 addendum. Repro commands reflect how Studio's adapter actually invokes `ah` (`ah --config <path> <subcommand>`); the operator should re-run each repro on the exact machine/version before filing, and prune anything that no longer reproduces on the version being filed against.

---

## Issue 1: `status --json` should emit a structured snapshot on daemon-absent, matching `events --format json`

**Labels (suggested):** bug, cli, consistency

### Summary

When no `ahd` daemon is running for a given config/state dir, `ah status --json` exits non-zero and prints a human-readable error string to stderr with **no JSON output at all**. In the identical situation, `ah events --format json` emits a well-formed, structured snapshot with `reason: "daemon_absent"`. The two commands are documented as reading the same underlying state contract, but only one of them stays machine-readable when that state is "no daemon".

This forces any structured consumer (this issue is filed from Studio's integration, but the problem is general) to either:
- special-case a non-zero exit + stderr text match for the daemon-absent case (re-introducing exactly the kind of brittle text-parsing the structured contract was meant to replace), or
- always start an `events` subscription just to get a decision-grade answer for a case `status` should be able to answer directly.

### Repro

Verified on ah 1.4.0 and 1.5.0 (same behavior on both):

```sh
# No ahd running for this config/state dir.
ah --config /path/to/some.toml status --json
# exit code: 1
# stdout: (empty)
# stderr: "ahd daemon is not running at <state dir>" (human-readable text, not JSON)

# Same config, same absent-daemon condition:
ah --config /path/to/some.toml events --format json
# stdout (one JSON line):
# {"reason":"daemon_absent","runtime_state":"inactive","ahd_alive":false, ...}
```

### Expected

`ah status --json` should, on daemon-absent, either:
- exit 0 (or a documented non-zero code reserved for this case) and print the same structured shape `events --format json` prints for `reason: "daemon_absent"` on stdout, or
- otherwise be explicitly documented as *not* a structured-output-guaranteed command in this state, so integrators know they must not treat a `status --json` failure as authoritative and must fall back to `events`.

Either resolution is workable for downstream consumers; the current silent asymmetry between the two "structured" read paths is the actual problem.

### Impact

Any consumer that calls `status --json` for a one-shot read (e.g., on first app launch, or to re-check state right after `stop`) currently cannot distinguish "daemon genuinely absent / inactive" from "some other status command failure" without either parsing stderr text or falling back to `events`. The most common real-world trigger is the most mundane one: first-ever open with no daemon yet, and post-`stop` re-check right after a successful close.

---

## Issue 2: state-dir resolution is inconsistent between `status`/`ps` and `events` when no `--config` is given

**Labels (suggested):** bug, cli, consistency, state-dir-resolution

### Summary

When run from the same current working directory (a directory that contains an `ah.toml`), without an explicit `--config` flag, `ah status` and `ah ps` resolve against the **default** state dir, while `ah events` resolves via **project discovery** (i.e., finds and uses the `ah.toml` in the cwd). All three commands are reading "the state for this project" from the user's point of view, but two of them and the third disagree about which state dir that even is.

This means a consumer that runs `status`/`ps` and `events` without threading an explicit `--config` through every call can observe the two read paths describing two different daemons/state dirs, with nothing in either output flagging the mismatch.

### Repro

Verified on ah 1.5.0, from a cwd that contains an `ah.toml`:

```sh
cd /path/to/project-with-ah-toml

ah status
# resolves against the DEFAULT state dir (not the project's ah.toml)

ah ps
# resolves against the DEFAULT state dir (same as `ah status`)

ah events --format json
# resolves via PROJECT DISCOVERY — uses the project's ah.toml / its state dir
```

No `--config` flag is passed in any of the three invocations above; the discrepancy is purely about default resolution order between the two command families.

### Expected

`status`, `ps`, and `events` should apply the same state-dir resolution order when invoked identically (same cwd, no explicit `--config`). Whichever order is intended to be canonical (project-discovery-first, matching `events`, seems most useful for interactive use inside a project directory) should be documented, and the other commands should be brought in line with it — or, if there is a deliberate reason for `status`/`ps` to default differently, that should be documented explicitly so integrators know not to assume all three agree by default.

### Impact

Any integrator (again, this is filed from Studio's adapter work, but applies to any tool that combines a one-shot `status`/`ps` read with an `events` subscription) that omits `--config` on some calls and not others can silently mix state from two different daemons/state dirs in a single UI decision, with no error surfaced. Where an explicit `--config` is always passed, this does not reproduce — but that shifts the burden entirely onto the integrator to remember to do so on every single invocation, with no CLI-side signal if they miss one.

### Related

This compounds Issue 1 above: a consumer trying to work around Issue 1 by falling back from `status` to `events` on daemon-absent must also account for the two commands potentially resolving to different state dirs in the first place.
