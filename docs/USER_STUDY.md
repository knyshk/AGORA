# RQ4 user study protocol (5–8 classmates, about 20 minutes each)

**Question:** does live collaboration with node takeover help people get a correct, trustworthy report,
compared with only watching the agents work?

## Setup (once)
1. `docker compose up -d`, `ollama serve` (see README), `cd frontend && npm run dev`.
2. Create one account per participant beforehand (Live Sessions → Register), or let them register.
3. The facilitator owns a **collaborative** session and shares the **editor** invite link.

## Design
Within-subjects, two conditions, order alternated between participants (A then B, or B then A):
- **A: watch only.** The participant may watch and review conflicts, but not take over nodes.
- **B: takeover allowed.** The participant may take over the drafting node and write or correct it.

Use a different task in each condition (task 1 and task 2 are matched in difficulty):
- Task 1: "Write a short report comparing Tesla and Ford revenue in 2022 and 2023 with a chart."
- Task 2: "Write a short report comparing Apple and Microsoft revenue in fiscal 2022 and 2023 with a chart."

## Steps per participant
1. Consent (below) and a 2-minute demo of the Live Sessions tab.
2. Condition 1: plan the run, (B only: take over a node if you want), start, review any conflict, export the report.
3. Questionnaire after condition 1 (below).
4. Condition 2 with the other task; questionnaire again.
5. Two open questions (below).

## What to record (results sheet: one row per participant × condition)
| participant | condition | task | time to final report (min) | report correct? (all figures match SEC) | conflicts resolved correctly? | took over a node? | SUS score | confidence 1–5 |
|---|---|---|---|---|---|---|---|---|

Time and correctness can be read from Run History and the exported report; the audit log shows who did what.

## Questionnaire (after each condition)
**SUS** (System Usability Scale, 1 = strongly disagree … 5 = strongly agree):
1. I think that I would like to use this system frequently.
2. I found the system unnecessarily complex.
3. I thought the system was easy to use.
4. I think that I would need the support of a technical person to be able to use this system.
5. I found the various functions in this system were well integrated.
6. I thought there was too much inconsistency in this system.
7. I would imagine that most people would learn to use this system very quickly.
8. I found the system very cumbersome to use.
9. I felt very confident using the system.
10. I needed to learn a lot of things before I could get going with this system.

SUS score = 2.5 × (Σ(odd items − 1) + Σ(5 − even items)), range 0–100.

**Confidence:** "How confident are you that the final report is factually correct?" (1–5)

## Open questions (end)
- What helped you most to trust (or distrust) the result?
- When did taking over a node help, and when was it unnecessary?

## Catch-up digest (synopsis RQ5): does it save time compared with reading the raw log?
Run once per participant, after the two conditions above.
1. While the participant is out of the room (2–3 minutes), the facilitator runs a task in the session that
   includes at least one conflict decision, one node takeover or redirect, and one finished node.
2. The participant returns and answers three questions: *Which node was redirected and why? Which figure
   won the conflict? Which agent wrote the chart?*
   - **Condition T (transcript):** they may only use the run's raw activity feed (Live activity / Run History).
   - **Condition D (digest):** they may only use "What did I miss?".
   Alternate T and D between participants (half each), using a different run for each.
3. Record the time to answer all three questions and how many answers are correct.

| participant | condition (T/D) | time to answer (s) | correct answers (0–3) |
|---|---|---|---|

## Consent text
"This is a short usability test of a BTech student project. We record the time you take, the runs you create
and your questionnaire answers. No personal data beyond your name and the email you use to log in is stored,
and results are reported anonymously. You can stop at any time."

## Reporting
Report each number with n (e.g. "SUS 78 ± 9, n = 6"), the per-condition means, and quotes from the open
questions. With 5–8 participants the study is indicative, not statistically conclusive; say so.
