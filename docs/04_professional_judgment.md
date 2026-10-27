# 04 — Professional Judgment

This document records the privacy, security, accessibility, and ethical decisions
behind the implementation. Each decision states the risk, the chosen response, and the
trade-off.

## 1. Duties and stakeholders

| Stakeholder | Duty of the system | Safeguard |
| :--- | :--- | :--- |
| Borrower | Collect only the personal data needed to process a request | Username, name, email, contact number only |
| Administrator | Make fair, attributable decisions | Role checks, recorded remarks, audit log |
| Custodian | Keep damaged assets out of circulation | Automatic maintenance routing, reconciliation |
| Instructor / evaluator | Verify individual and team contribution | Git history, requirement-grouped tests, evidence documents |
| Institution | Comply with privacy and records rules | Data minimisation, no third-party student records, retention-friendly archiving |

## 2. Access control

| Concern | Decision | Implementation |
| :--- | :--- | :--- |
| Only admins manage inventory | Central role checks on every admin view | `admin_required` decorator in `views.py` |
| Only basic users use the portal | Central portal role checks | `basic_user_required` decorator |
| Admins can still reach the portal landing route | Redirect to the dashboard rather than showing a broken page | `portal_home` role-aware redirect |
| Users must not read other users' requests | Filter by the signed-in owner | `request_history` filters `user=request.user` |
| Users must not cancel another user's request | 404 when the request is not owned | `get_object_or_404(..., user=request.user)` |
| Role cannot be self-assigned | Registration form has no role field | `RegisterForm` forces `BASIC_USER` |
| Activation cannot be self-assigned | Registration ignores posted `is_active` | `RegisterForm.save()` sets an active basic user |
| Profile edits cannot change role | Model form exposes only personal details | `UserProfileForm` fields |
| Deactivated users cannot sign in or transact | Both Django `is_active` and profile flag are checked | `admin_required`, `basic_user_required`, login form |
| No accidental lockout | An admin cannot deactivate their own account | `toggle_account_status` guard |
| Detail pages and reports are protected | Admin-only decorator on every report/export/history view | `account_detail`, `overdue_report`, `overdue_report_csv`, CSV views |

Trade-off: cross-role requests return **403 Forbidden** instead of redirecting. This
is deliberate: it avoids leaking which area a user tried to reach and makes the denial
explicit in tests.

## 3. Data protection

| Concern | Decision |
| :--- | :--- |
| Passwords | Stored only as Django password hashes; never logged or displayed |
| Secrets | `SECRET_KEY`, `DEBUG`, and `ALLOWED_HOSTS` come from environment variables; `.env` is git-ignored and `.env.example` contains no real key |
| CSRF | All state-changing views are POST-only and use `{% csrf_token %}` |
| SQL injection | All queries go through the ORM; no raw SQL |
| XSS | Templates auto-escape user content (`purpose`, descriptions, remarks) |
| Sensitive data in exports | CSV escapes cells beginning with `=`, `+`, `-`, `@` to prevent spreadsheet formula injection |
| Demo credentials | Demo accounts only; the README warns not to reuse them |
| Private data in seed | The team's own names, used with consent, plus invented dummy identities; no third-party student or staff records are seeded |
| Production guidance | README documents key generation and `DEBUG=0`; a separate production settings module is not required |

The brief asks for environment-variable guidance rather than a production deployment.
The implemented settings loader reads `.env` when present and falls back to a clearly
labelled development key, so a clean clone still runs without committing a secret.

## 4. Record integrity and retention

| Decision | Reason |
| :--- | :--- |
| Archive categories/items instead of deleting | Requests, loans, and returns must remain explainable years later |
| `PROTECT` foreign keys on catalog items and units | Prevents accidental deletion of referenced history |
| Retire units instead of deleting | Preserves maintenance and loan history |
| Keep deactivated accounts | Historical requests still need an owner |
| Keep released allocation rows | A unit can be borrowed again without losing its earlier assignment history |
| Never rewrite audit entries | The audit trail must be append-only in normal operation |
| Record who performed each action | `AuditLog.actor`, `Loan.issued_by`, `ReturnRecord.received_by`, `MaintenanceRecord.handled_by` |
| Store a reason for rejection and due-date changes | Decisions must be reviewable by the borrower and the instructor |
| Route damaged units to maintenance automatically | Prevents damaged equipment from returning to the available pool |

Trade-off: archived records and retained allocations make listings noisier. The UI
filters active rows by default, and reconciliation screens show the full picture to
admins.

## 5. Fairness and operational judgment

| Scenario | Judgment |
| :--- | :--- |
| Two admins approve the last unit | Only one succeeds; the other receives an error and the request stays Pending |
| A borrower cancels after approval | Reserved units are released, so other borrowers are not blocked |
| A unit is returned damaged | It cannot be reissued; it enters Maintenance and requires an action before release |
| A due date must change | Admins must record a reason and the change is audited |
| A requested quantity exceeds limits | Rejected at form validation and again at approval |
| A request is overdue | Computed live and shown on dashboards, lists, and the overdue report; no manual status drift |
| Inventory counts disagree with allocations | A reconciliation panel lists anomalies; orphaned reservations can be released with one audited action |
| A catalog item has history | It is archived, never deleted |
| A user is deactivated | Sign-in is blocked, but their history remains readable to admins |
| A reviewer is about to approve a request with insufficient stock | The queue shows current availability and an `Insufficient` warning; approval still validates atomically |

## 6. Accessibility, bias, and public welfare

- **Accessibility:** tables have header cells, form controls have labels, navigation has
  breadcrumbs and a skip link, and every page has one `h1` with an ordered heading
  outline. Status badges always include text so meaning does not depend on colour,
  focus is visible, menus and dialogs are keyboard-operable, and layouts reflow from
  desktop to mobile widths.
- **Bias:** approval is based on recorded quantities and availability, not on an
  opaque score. The reviewer sees the same inventory data for every requester.
- **Public welfare:** damaged units are removed from circulation, reducing the risk of
  injury or equipment failure. Retired units cannot be reissued.
- **Conflict of interest:** an administrator cannot deactivate their own account, and
  every decision is attributed. Separation between the borrower and reviewer roles is
  enforced server-side.
- **Accountability:** the audit page lists actor, action, timestamp, and details for
  approvals, rejections, cancellations, releases, returns, maintenance, account
  changes, and catalog changes.

## 7. Legal and policy context

| Law / policy | How the project responds |
| :--- | :--- |
| Data Privacy Act of 2012 (RA 10173) | Collects minimal personal data, prevents cross-user disclosure, and seeds only the team's own names (with consent) plus invented dummy identities |
| Intellectual Property Code (RA 8293) | Uses Django and Bootstrap under their licences; no proprietary code is copied |
| BulSU AI Policy | AI assistance is disclosed; the team can explain and demonstrate the submitted behaviour |
| Institution records policy | Archive/retire instead of deleting transactional records |
| Course specification | No Django admin, exactly two roles, all access checks server-side |

## 8. Limitations and honest disclosures

- The development server and fallback `SECRET_KEY` are for demonstration only.
- SQLite serialises writes; the locking code is written to be correct on a production
  database but is not load-tested.
- There is no email verification or password-reset email delivery; Django's default
  views are present but email is not configured.
- Audit logs are append-only by convention; there is no database-level trigger that
  blocks edits by a database administrator.
- The interface is light-theme only and intentionally avoids a client-side framework or
  build step; interactivity is progressive enhancement over working HTML.
- The evidence folder contains seeded screenshots of all principal screens, so an
  unexpected display issue during the defense does not hide the implemented UI.

## 9. Incident record

**Incident:** after the first working return workflow, a returned unit could not be
allocated to a new request because `UnitAllocation` had an unconditional unique
constraint on `unit`.

**Impact:** A5 return worked visually, but a later A3 approval failed for any unit that
had ever been borrowed. This blocked a core end-to-end scenario.

**What was tried:** deleting allocation rows on return fixed the symptom but destroyed
the audit trail and contradicted the "keep history" decision.

**Resolution:** `UnitAllocation` gained `allocated_at`, `released_at`, and
`release_reason`; returns and cancellations now release rows, and the uniqueness
constraint applies only while `released_at IS NULL`. Tests cover reallocation after a
return, competing approvals for the last unit, and cancellation history.

**Lesson:** history-preserving state changes are safer than destructive deletes, even
when the delete is the quickest fix.

## 10. Instructor feedback

No written instructor feedback had been received at the time this package was prepared.
The team's response process is:

1. Record the feedback verbatim in this document.
2. Map it to a requirement ID and the affected files.
3. Add a failing test before changing behaviour.
4. Re-run the full suite and update this section with the resolution.

Any feedback received during the defense will be appended here before the final
submission.

## 11. Evidence

- `tests/test_auth_routing.py` — cross-role 403 behaviour, registration cannot set a
  role, deactivated-account handling.
- `tests/test_requests_release.py` — required rejection reason, atomic approval,
  competing approvals, due-date revision.
- `tests/test_returns_maintenance.py` — damaged routing, return history, maintenance
  close.
- `tests/test_reports_settings.py` — admin-only report exports and audit entries.
- `docs/evidence/tests.txt` — full passing run.
- `docs/evidence/screenshots/` — seeded views of the admin and basic-user areas used to
  verify labels, empty states, and access-controlled navigation.
