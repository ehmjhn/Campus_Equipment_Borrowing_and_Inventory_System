# 06 — Communication Guides

## 1. Demonstration plan (12 minutes + 3 minutes Q&A)

| Time | Segment | Owner | What to show |
| :--- | :--- | :--- | :--- |
| 0:00–1:00 | Problem and goals | Alexander Azotes | Manual logbook pain points, double-booking, lost history, two user groups |
| 1:00–1:45 | Roles and architecture | Jhon Emmanuele Alcañices | Exactly two roles, `/manage/` vs `/portal/`, no Django admin, MTV request path |
| 1:45–3:00 | U1/U2 | Ian Joshua Lizano | Register, sign in, land on `/portal/`, search catalog, serviceable vs available counts |
| 3:00–4:30 | U3/U4 | Marc Renzo Bulaong | Submit a two-item request, show Pending, cancel, show released units and history |
| 4:30–6:00 | A1/A2 | Jhon Emmanuele Alcañices | Search accounts, open account history, deactivate/reactivate; create category/item/unit; filter units; retire/restore |
| 6:00–8:00 | A3/A4 | Jhon Emmanuele Alcañices / Daniel Alejandrino | Filter and approve the pending request, show live availability and reserved units, release, print borrowing slip |
| 8:00–9:30 | A5/A6 | Daniel Alejandrino / Jerome San Pedro | Partial return, damaged return → maintenance, close maintenance, reconciliation panel |
| 9:30–10:30 | A7 | Jerome San Pedro | Live cards/charts, loan report, date-filtered CSV, overdue report and CSV |
| 10:30–11:15 | A8 | Jerome San Pedro | Audit log search and settings change |
| 11:15–12:00 | Tests and lessons | Jhon Emmanuele Alcañices / Ian Joshua Lizano | 123 passing tests, competing-approval test, one lesson learned |

Every member has an identifiable segment. Hand-offs should be rehearsed so the total
stays under 12 minutes.

### Demo data to prepare

1. Run `python manage.py seed`.
2. Sign in as `ij.lizano` / `alab_lizano.123` in one browser profile.
3. Sign in as `je.alcanices` / `alab_alcanices.123` in a second browser profile or
   incognito window.
4. Keep a Pending request ready for the live approval.
5. Keep one Available unit ready for retirement/restoration.
6. Keep one Issued loan ready for a partial/damaged return.
7. Open the overdue report before the demo so the rows are already loaded.

### Failure-proofing

- Have screenshots of every screen in case the network or projector fails.
- Do not rely on creating data live for the first time; rehearse the exact sequence.
- If a live action fails, read the validation message, explain why the system rejected
  the action, and continue with the prepared dataset.
- Keep the CSV downloads and the test evidence file open in separate tabs.

## 2. Slide outline and speaker allocation

| Slide | Content | Speaker |
| :--- | :--- | :--- |
| 1 | Title, course, section BSIT 4F-G1, six members, submission date | Jhon Emmanuele Alcañices |
| 2 | Problem: availability blindness, double-booking, untracked damage | Alexander Azotes |
| 3 | Roles and 75/25 split: A1–A8 vs U1–U4, no Django admin | Jhon Emmanuele Alcañices |
| 4 | MTV architecture, ERD, route map | Jhon Emmanuele Alcañices |
| 5 | Workflow: Pending → Approved → Issued → Returned, cancellation and overdue | Daniel Alejandrino |
| 6 | Security and integrity: role decorators, atomic approval, constraints, audit | Jerome San Pedro |
| 7 | Live demo, split by the segments above | All members |
| 8 | Test results: 123 tests, seed coverage, migration check | Ian Joshua Lizano |
| 9 | Challenges and lessons: allocation history, concurrency, time management | Daniel Alejandrino |
| 10 | Individual contributions and Q&A | Marc Renzo Bulaong (coordination) |

## 3. Q&A bank

| Likely question | Short answer |
| :--- | :--- |
| Why not use Django admin? | The specification prohibits it. Every admin feature is a custom view under `/manage/` with its own role check. |
| How do you prevent double issuance? | A unit must be `Available`, is locked with `select_for_update()`, active allocations are excluded, and a conditional unique constraint applies while `released_at IS NULL`. |
| What happens if two admins approve at once? | One transaction commits; the other sees the unit no longer available and leaves its request Pending. |
| Where is the 75/25 split? | Eight admin areas (A1–A8) versus four user areas (U1–U4). |
| How is overdue handled? | It is computed from the due date and current date; it is never a stored status. The returns page and a dedicated report show outstanding units and overdue days. |
| Why keep deactivated accounts? | Their request/loan history must remain explainable. |
| Why archive instead of delete? | Deleting would destroy transaction history; `PROTECT` foreign keys enforce this. |
| Why keep released allocations? | A unit can be borrowed again without losing its earlier assignment history; the conditional constraint permits a new active row. |
| How do you know who did what? | Every sensitive action writes an `AuditLog` row with actor, timestamp, action, and details. |
| How is role escalation prevented? | Registration has no role field; profile editing excludes role and activation; admins manage activation. |
| Can a user cancel someone else's request? | No. The lookup is scoped to `user=request.user`, so a foreign request returns 404. |
| What does a basic user see? | Active catalog items, total serviceable and available quantities, their own request history, and public descriptions. Borrower identities, audit records, internal notes, and maintenance details are hidden. |
| How is CSV injection handled? | Cells beginning with `=`, `+`, `-`, or `@` are prefixed with an apostrophe. |
| What would you change for production? | PostgreSQL, environment-managed secrets, `DEBUG=False`, HTTPS, a production WSGI server, and a real email backend. |
| What was the hardest bug? | Returned units could not be re-borrowed because the first allocation row was uniquely constrained forever. We replaced deletion with `released_at`/`release_reason` history and a conditional active-only constraint. |
| What did each member learn? | Emman: transactional invariant design; Daniel: state transitions and per-unit recovery; Jerome: ORM aggregates and report consistency; Ian: role-aware routing; Renz: ownership scoping and form validation; Alexander: acceptance criteria and privacy review. |
| What would you improve next? | Add HTMX partial updates or a notification queue, but only after the current tests and documentation are complete. |

## 4. Progress update (final week)

```text
Week: October 22–28, 2026 (finals week)
Done:
  - A1–A8 admin workflows and U1–U4 portal implemented (models, views, templates)
  - Conditional allocation history and re-borrowing fixed (models.py, views.py)
  - Review availability, account history, unit filters, overdue report added
  - 123 automated tests passing; system and migration checks clean
  - Seed command rebuilt with 3 categories, 6 items, 24 units, 22 requests, 8 loans
  - Documentation/evidence folder completed and packaged
In progress:
  - Final 12-minute rehearsal and screenshot capture (all members, October 28)
Blocked:
  - None
Risks:
  - Vendored Bootstrap and layered custom CSS keep the demo independent of the network
Next week:
  - Defense and Q&A; record instructor feedback in docs/04_professional_judgment.md
```

## 5. Incident / blocker message (worked example)

```text
What happened: A returned unit could not be allocated to a new request.
Impact: A5 return worked, but later A3 approvals failed for any unit with history.
What I tried: Deleting allocation rows fixed the symptom but erased the audit trail.
What I need: Agreement on a history-preserving allocation model.
Proposed next step: Add allocated_at/released_at/release_reason, make the uniqueness
constraint conditional on active allocations, and add re-borrowing tests.
```

This is the real incident described in `docs/04_professional_judgment.md`.

## 6. Code review request (worked example)

```text
Branch: user-portal-dev
Requirement: U1–U4
What changed: Basic-user URL routes, U3 request submission, U4 history/cancellation,
  portal templates, and tests.
How to test:
  1. Run python manage.py test Campus_Equipment_Borrowing_and_Inventory_System_APP.tests.test_portal
  2. Sign in as je.alcanices, submit a two-item request, cancel it, and confirm units return.
Expected result: Request is Pending on submit; cancellation returns units to Available
  and keeps the released allocation history.
Risks: Ownership scoping and the interaction between cancellation and reservations.
```

Merged as pull request #1:
<https://github.com/ehmjhn/Campus_Equipment_Borrowing_and_Inventory_System/pull/1>

## 7. Technical setup guide for developers

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py seed
python manage.py test
python manage.py runserver
```

Read `README.md` for routes, roles, business rules, and test module mapping. Never
commit `.env`, `db.sqlite3`, virtual environments, caches, or IDE folders.

## 8. Basic-user guide

1. Open `/accounts/register/` and create an account. Registration always creates a
   BASIC USER.
2. Sign in. You land on `/portal/`.
3. Browse or search the catalog. `Total serviceable` excludes retired and maintenance
   units; `Available now` counts units that can be reserved immediately.
4. Open the request form, choose one to three different items, enter quantities, a
   purpose, and a return date, then submit. The request is Pending and does not reserve
   units yet.
5. Open `/portal/requests/` to track status, due dates, released/returned units, and
   admin remarks.
6. Cancel a Pending or Approved request before issue. Reserved units return to the pool.
7. Edit only your name, email, and contact number at `/portal/profile/`. Role and
   activation cannot be changed.

## 9. Administrator guide

1. Sign in as an administrator. You land on `/manage/`.
2. **Accounts:** search accounts, open an account history, and activate/deactivate.
3. **Catalog:** create categories, items, and individual units with unique asset codes.
   Archive master records instead of deleting them.
4. **Request review:** filter by status/date, check `Available now`, then approve or
   reject with a reason. Approval reserves specific units atomically.
5. **Release:** issue an approved request, revise its due date with a reason if needed,
   and print the borrowing slip.
6. **Returns:** record each unit's condition. Damaged units go to Maintenance; the loan
   closes only when every unit is returned.
7. **Maintenance:** open a record for a unit that is not Reserved/Issued, then close it
   with the action taken so the unit becomes Available.
8. **Reports:** use the dashboard date range, loan report, equipment CSV, and overdue
   report/CSV.
9. **Audit/settings:** search the audit trail and update the maximum loan duration and
   requested quantity.

## 10. Evidence

- `docs/evidence/tests.txt` — 123-test final run.
- `docs/evidence/seed.txt` — demo dataset counts.
- `docs/evidence/check.txt`, `makemigrations_check.txt` — release checks.
- `docs/evidence/git_graph.txt` — branch and commit graph.
- `docs/evidence/screenshots/` — seeded dashboard, review queue, return screen, catalog,
  request form, history, and supporting admin pages for the projector fallback.
- The slide outline above is the final deck structure; each speaker owns the listed
  slide and the corresponding live segment.
