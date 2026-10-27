# 01 — User Needs

## 1. Purpose and discovery

The Campus Equipment Borrowing and Inventory System serves two groups: campus
equipment administrators and borrowers (students or faculty). The requirements were
derived from the instructor's Final Project, reviewed by all six team members
in class consultation and asynchronous discussion, and validated through acceptance
testing of the delivered workflows.

| Item | Detail |
| :--- | :--- |
| Primary source | `IT 401W - Project (Equipment Borrowing) - 1st Sem 26-27 (1).docx` |
| Discovery method | Requirements analysis, class consultation, team review, scenario walkthroughs |
| Respondents | Six BSIT 4F-G1 team members acting as administrator and borrower proxies |
| Requirement review date | October 22–25, 2026 |
| Acceptance validation | 123 automated tests plus a seeded end-to-end demo walkthrough |

No external interviews were conducted. The observations below are the pain points
stated in the brief and confirmed during the team's walkthrough, not quotations from
named individuals. Replacing this paragraph with real interview notes is the only
group-supplied improvement that would strengthen this section.

## 2. Stakeholders and personas

| Persona | Role | Goals | Pain points addressed |
| :--- | :--- | :--- | :--- |
| Campus equipment administrator | ADMIN | Keep an accurate inventory, approve fair requests, release and recover units, keep history | Double-booked assets, untracked damage, manual logbooks, no audit trail |
| Student / faculty borrower | BASIC USER | Find available equipment, request it, track status, cancel when plans change | Not knowing availability, no status visibility, paperwork |
| Laboratory custodian | ADMIN (same role) | Record damage and repairs, reconcile counts | Units stuck in the wrong state, lost maintenance history |

Observed pain points:

- A borrower cannot tell from a paper catalog whether an asset is physically free,
  already reserved, or under repair.
- Two staff members can promise the same asset to different borrowers because the
  logbook has no single source of truth.
- Damage discovered at return is often recorded late or not at all, so the next
  borrower may receive a defective unit.
- Cancellations are difficult to trace, so reserved units remain blocked after a
  borrower changes plans.

## 3. Needs → requirements

| Need | Requirement | Delivered evidence |
| :--- | :--- | :--- |
| Know which asset is free | U2, A2 | Catalog shows total serviceable and available-now counts; admin unit list filters by category, item, and status |
| See availability while reviewing | A3 | Review queue shows `Available now` for each requested item and warns when stock is insufficient |
| Never issue the same unit twice | A3, A4, section 7 | Conditional `UnitAllocation` uniqueness, row locks, transaction blocks, competing-approval test |
| Approve atomically | A3 | All-or-nothing reservation; insufficient stock leaves the request Pending |
| Understand decisions | A3, U4 | Required rejection reason, admin remarks, status labels in the borrower history |
| Change plans without blocking others | U4 | Cancel Pending/Approved requests; reservations are released and kept in history |
| Recover equipment in parts | A5 | Per-unit `ReturnRecord`, `Partially Returned` status, loan closes only after the last unit |
| Handle damaged equipment | A5, A6 | Damaged returns route the unit to Maintenance; repair action is required before release |
| Trust the numbers | A7, A6 | Live dashboard cards, loan report, reconciliation panel, date-filtered CSV exports |
| Spot overdue loans quickly | A5, A7 | Overdue list on the returns page and a dedicated overdue report with CSV export |
| Investigate past actions | A8, A1 | Searchable audit log and per-account borrowing history |
| Keep records instead of deleting them | A2 | Archive flags, `PROTECT` foreign keys, Retired unit state |
| Protect personal data | U1, section 7 | Users edit only their own profile; role and activation are admin-only |

## 4. Non-functional needs

| Need | Target | How it is met |
| :--- | :--- | :--- |
| Usability | A borrower can request equipment in under 2 minutes | Catalog prefill, one to three item rows, inline validation, explicit empty states |
| Traceability | Every sensitive action is attributable | `AuditLog` written inside the same transaction as the change |
| Reliability | No partial approval, release, or return | `transaction.atomic()` plus `select_for_update()` |
| Security | Only the correct role can perform an action | Server-side decorators, ownership filters, POST-only mutations |
| Accessibility | Status must not rely on colour alone | Text status labels and table headers accompany colour badges |
| Safety | Irreversible actions ask for confirmation | Confirmation prompts on approve, reject, issue, return, archive, retire, restore, deactivate, and close-maintenance actions |
| Portability | Runs on a typical student laptop | Python + SQLite + Django only |

## 5. Usability and acceptance testing

The team used scripted acceptance scenarios that map directly to the requirements:

| Scenario | Expected result | Automated evidence |
| :--- | :--- | :--- |
| Borrower submits a request with two different items | Pending request, no unit reserved | `test_portal.py::RequestSubmissionTests` |
| Borrower submits the same item twice or exceeds the limit | Form error, no partial request saved | `test_inventory_rules.py`, `test_portal.py` |
| Two admins approve the last available unit | Exactly one approval succeeds | `test_requests_release.py::test_competing_approvals_for_last_unit_allow_only_one` |
| Borrower cancels an approved request | Reserved unit returns to Available and history is retained | `test_portal.py::RequestHistoryTests` |
| Admin returns one of two units | Loan remains Partially Returned | `test_returns_maintenance.py` |
| Damaged unit is returned | Unit enters Maintenance, not Available | `test_returns_maintenance.py` |
| A repaired unit is closed from maintenance | Unit becomes Available again | `test_returns_maintenance.py` |
| Basic user opens an admin route | HTTP 403 | `test_auth_routing.py`, `test_admin_accounts.py` |
| Admin filters the review queue by date | Only matching requests appear | `test_requests_release.py` |
| Admin downloads the overdue CSV | Rows match the overdue report | `test_reports_settings.py::OverdueReportTests` |

Resolved issues found during acceptance testing:

1. **Unit re-borrowing was blocked after a return.** The original allocation row was
   unique forever. It was replaced with `released_at` / `release_reason` history and a
   conditional constraint that applies only to active allocations.
2. **Competing approvals could read stale availability.** Approval now filters out
   active allocations explicitly after locking candidate units.
3. **The review queue did not show current stock.** Each row now displays
   `Available now` and an `Insufficient` warning before the admin approves.
4. **Cancellation deleted history.** Cancellation now marks allocations as released,
   preserving an auditable trail.

Enhancement responding to the changed requirement: the brief asks for current
availability during review and separate overdue reporting. Both were added after the
first working version, together with tests, rather than being left as documentation
claims.

## 6. Maintenance guidance

- Keep `README.md` and `.env.example` in sync with any new environment variable.
- Run `python manage.py test` before every merge; the suite is grouped by requirement.
- Run `python manage.py makemigrations --check --dry-run` before packaging.
- Add new catalog states or workflow transitions through a migration, never by manual
  database edits.
- Rotate `DJANGO_SECRET_KEY` outside the demonstration environment and never commit
  `.env`.

## 7. Out of scope

- Third roles (staff, supervisor, technician) — prohibited by the specification.
- Payment, fines, or procurement workflows.
- Email/SMS notifications.
- Native mobile application.
- Production hosting and load testing.

## 8. Evidence

- `docs/evidence/tests.txt` — full 123-test run with runtime.
- `docs/evidence/check.txt` — `manage.py check` result.
- `docs/evidence/makemigrations_check.txt` — schema/migration consistency.
- `docs/evidence/seed.txt` — reproducible demo dataset counts.
- `docs/evidence/environment.txt` — verification machine and versions.
- `docs/evidence/screenshots/` — seeded catalog, request form, history, dashboard,
  review queue, accounts, physical units, release, returns, maintenance, audit, overdue,
  and profile screens used as the defense fallback.
