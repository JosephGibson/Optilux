# Plan template
Status: the template every docs/plans/m<N>.md follows section by section, in use since plans/m0.md.

## Contents
Rules · Template · Filling it

## Rules
- File: docs/plans/m<N>.md, at most 40,960 bytes (workflow.md#docs-rules), ASCII, LF without BOM, a `## Contents` line after the Status line.
- Sections: exactly the ten below, in this order, with these headings. A section with nothing to say holds the word "none"; none is dropped, renamed or added.
- Premises: every fact the plan rests on is a row in section 3 with its source and how it was verified, dated. A source is a doc heading (path#heading), a config key (file: key), a file on disk, a command with its output, or a URL. "Described" is not verified: ALC's recurring failure was a control described rather than read (workflow.md#running-a-milestone). A premise that could not be verified says "open:" and what would decide it; no phase rests on it.
- Phases: `M<N>.P<PP>`, M<N>.P00 the plan itself; each is one reviewable outcome of one or more test-green commits (workflow.md#git) with its change, tests, exit and estimate. The commits are written when they are made, never in the plan. Estimates are agent hours; machine time is listed apart and does not count toward the sizing rule (design.md#6-milestones).
- Decisions: each carries an owner (user or Claude) and the recommendation an unattended run takes (workflow.md#running-a-milestone). A closed decision (design.md#7-decisions-taken-user-2026-10-05) is cited, never reopened. Decisions that belong to the sequence of milestones live in roadmap.md#decisions; the plan adds only its own.
- Cites: by path and heading or quoted content, never by line number. No time-sensitive instructions; superseded text is deleted, not archived.
- The roadmap holds the milestone's place, its exit, the findings assigned to it and each phase in brief (change, exit, estimate); the plan holds the detail (files, tests, decisions), which the roadmap cites rather than copies.
- Size: a plan that would pass the cap splits the milestone before it starts (design.md#6-milestones).
- Review: the user approves the plan (section 10) before its prompt set is written; /critique is optional, and each finding is folded in after verification at its source or listed with a reason in the handoff.

## Template
Copy the block, replace every `<...>`, keep everything else.

```markdown
# M<N> <name>
Status: <draft | approved by the user, <date>>; <one sentence on what the milestone delivers>.

## Contents
1 Goal and exit · 2 Scope · 3 Premises · 4 Ground rules · 5 Phases · 6 Decisions · 7 Stop conditions · 8 Estimates · 9 Handoff · 10 Approval

## 1. Goal and exit
- Goal: <one sentence>.
- Exit (roadmap.md#<milestone heading>): <conditions, each checkable by a command, a test or a record>.

## 2. Scope
- In: <verbs, skills, agents, docs, configs, mod commands>.
- Out: <what a reader might expect here, with the milestone that owns it>.

## 3. Premises
| # | Premise | Source | Verified |
|---|---|---|---|
| P1 | <fact> | <path#heading / file: key / command / URL> | <how, date; or open: <what decides it>> |

## 4. Ground rules
- <what is never touched, what is announced, limits, the named stops, how the run ends>.

## 5. Phases
### M<N>.P<PP> <title>
- Change: <files and behaviour>.
- Tests: <what proves it; "by hand: <check>" where no test is cheap>.
- Exit: <checkable>.
- Estimate: <h> h; machine: <launches, downloads, or none>.< Attended: <what needs the user>.>

## 6. Decisions
| Id | Decision | Owner | Recommendation | When |
|---|---|---|---|---|
| D<n> | <question> | <user or Claude> | <the option an unattended run takes, with what the alternative would cost> | <phase> |

## 7. Stop conditions
- <stop, record and report; never work around>.

## 8. Estimates
- Agent: <sum> h (<per phase>); basis: <ALC or spike figures>.
- Machine: <if any, else none>.
- Tripwire standing (roadmap.md#estimates): <M0-M3 summed estimates and the actuals so far>.

## 9. Handoff
- <what docs/handoff.md must hold at the stop: its `Last phase:` line, what passed, failed, deferred; commits and time against estimates; questions; the next command>.

## 10. Approval
- <draft, <date> | approved by the user, <date>, with any change asked for>.
```

## Filling it
- Write section 3 first, from the sources, then the phases: a phase that rests on an unverified premise is not planned yet.
- Estimates: ALC's phases took about 1 h (workflow.md#git); the spike estimated 4 h and took 2.5 h; ALC's run estimates of 4-6 h took about 1.2 h (workflow.md#running-a-milestone). Estimate in hours, keep the actuals in the handoff, recompute the tripwire.
- Prompts (docs/prompts/m<N>.md) are written after approval: one per phase plus Resume, each self-contained, in the format `optilux status` parses (workflow.md#running-a-milestone).
- When the milestone closes, the roadmap's section for it shrinks to one line; the plan stays as the record of what was planned, and the handoff holds what happened.
