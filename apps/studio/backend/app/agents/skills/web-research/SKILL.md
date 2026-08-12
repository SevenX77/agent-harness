---
name: web-research
description: Read pages on the live web — including provider documentation, model catalogues and console pages that only exist behind a signed-in account — through the person's own browser. Use when a question needs a fact from a vendor's site rather than from this repository, when a page returns a login wall, or when a capability claim needs a documented source.
---

# Skill: Web Research

Read the web through `fetch_web_page`. It drives the browser the person is
**already signed into**, so a page that needs an account is readable without
anyone handing over a credential.

## 1. Reading a page

1. Call `fetch_web_page` with the URL.
2. If the response carries `continues_at`, the page was longer than one chunk.
   Call again with `start` set to that number, and keep going until
   `continues_at` is null. A conclusion drawn from chunk one of five is a guess.
3. Quote what the page says. Paraphrase invites drift, and the whole point of
   reading the source is to stop guessing.

## 2. When the browser bridge is not ready

The tool returns an error whose text is **an instruction for the person**, not a
description of the page. Treat the two as completely different outcomes:

- **Never** report "this provider documents nothing" or "the page is empty" —
  the truth is that nobody opened Chrome.
- Relay the instruction in your own words, say plainly that you will wait, and
  stop. Do not retry in a loop; nothing changes until a human acts.
- When they say they are done, call the tool again.

## 3. What this skill will not do

- **Never ask for a password, a verification code, or an exported cookie.**
  Signing in is the person's job and only theirs. If a page needs a login, ask
  them to log in — never offer to do it for them.
- The tool cannot click, type, fill, submit or run scripts, by construction.
  Do not look for another way around that: acting inside somebody's signed-in
  browser acts **as them**.
- Do not read private accounts you have no business reading, paid content, or
  anything gated by an anti-bot check. Do not work around such a check.

## 4. Recording what you found

A fact read off a vendor's page is evidence, and evidence is ranked by who said
it and whether anyone else can check it:

- A page **anyone can open** at that URL supports a `provider_doc` claim.
  Record the URL alongside the claim.
- A page that **only opened because this person is signed in** cannot be
  checked by anybody else — a different machine or account gets a login wall.
  It is therefore an `agent_draft`: a documented starting point that still owes
  a real measurement. Say so explicitly rather than letting it pass as
  `provider_doc`.
- Reading a claim is never the same as testing it. If the route can be probed,
  probe it; the measurement outranks the page.

## 5. Anti-patterns

- ❌ Concluding from a login wall that a capability does not exist.
- ❌ Stopping at the first chunk of a long page.
- ❌ Recording a signed-in page as publicly-documented evidence.
- ❌ Retrying the tool repeatedly while waiting for someone to open Chrome.
