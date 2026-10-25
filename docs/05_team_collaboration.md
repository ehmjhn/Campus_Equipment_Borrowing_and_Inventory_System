# 05 — Team Collaboration

## 1. Team

Course section: **BSIT 4F-G1**  
Project: **IT 401W Final Project A — Campus Equipment Borrowing and Inventory System**  
Submission date: **October 28, 2026**

| Member | Student number | Primary responsibility | Backup / reviewer |
| :--- | :--- | :--- | :--- |
| Jhon Emmanuele S. Alcañices | 2023100224 | Shared foundation, A1–A3, layout architecture, integration, packaging | Daniel Alejandrino |
| Daniel B. Alejandrino | 2023104581 | A4 release, A5 returns, A6 maintenance integration | Jerome San Pedro |
| Alexander A. Azotes | 2023105498 | U1/U2 acceptance testing, documentation review, presentation segment | Ian Joshua Lizano |
| Marc Renzo D. Bulaong | 2023100233 | U3 request submission, U4 tracking and cancellation | Ian Joshua Lizano |
| Ian Joshua L. Lizano | 2023103575 | Basic-user routing and landing page, U1 registration/profile review | Marc Renzo Bulaong |
| Jerome M. San Pedro | 2023100179 | A6 maintenance, A7 dashboard/reports, A8 audit/settings | Daniel Alejandrino |

The table is the group's submitted ownership plan. The commit record in section 3 is
the factual record of who pushed each code change.

## 2. Ownership by module

| Area | Files | Owner |
| :--- | :--- | :--- |
| A1 Account management | `views.account_management`, `views.account_detail`, `views.toggle_account_status`, `templates/manage/accounts.html`, `templates/manage/account_detail.html`, `tests/test_admin_accounts.py` | Jhon Emmanuele Alcañices |
| A2 Catalog & units | `views.category_*`, `views.catalog_item_*`, `views.equipment_unit_*`, `views.physical_units_management`, `templates/manage/categories.html`, `templates/manage/catalog_items.html`, `templates/manage/physical_units.html`, `tests/test_catalog_units.py` | Jhon Emmanuele Alcañices |
| A3 Review | `views.request_review`, `views.request_approve`, `views.request_reject`, `templates/manage/request_review.html`, `tests/test_requests_release.py` | Jhon Emmanuele Alcañices |
| A4 Release | `views.release_management`, `views.issue_approved_request`, `views.revise_approved_due_date`, `views.borrowing_slip`, templates, tests | Daniel Alejandrino |
| A5 Returns | `views.return_management`, `views.record_unit_return`, `templates/manage/return_management.html`, `tests/test_returns_maintenance.py` | Daniel Alejandrino |
| A6 Maintenance | `views.maintenance_management`, `views.open_maintenance_record`, `views.close_maintenance_record`, `views.reconcile_inventory`, templates, tests | Jerome San Pedro |
| A7 Reports | `views.admin_dashboard`, `views.dashboard_report_csv`, `views.overdue_report`, `views.overdue_report_csv`, `templates/manage/dashboard.html`, `templates/manage/overdue_report.html`, `tests/test_reports_settings.py` | Jerome San Pedro |
| A8 Audit/settings | `views.audit_settings_management`, `templates/manage/audit_settings.html`, `tests/test_reports_settings.py` | Jerome San Pedro |
| U1–U2 Portal | `views.register`, `views.portal_home`, `views.profile_view`, `views.browse_catalog`, `templates/portal/catalog.html`, `templates/portal/profile.html`, `templates/registration/`, `tests/test_auth_routing.py`, `tests/test_portal.py::CatalogTests` | Ian Joshua Lizano, Alexander Azotes (review) |
| U3–U4 Portal | `views.borrow_request_create`, `views.request_history`, `views.cancel_borrow_request`, `templates/portal/request_form.html`, `templates/portal/request_history.html`, `tests/test_portal.py` | Marc Renzo Bulaong |
| Shared foundation | `models.py`, `forms.py`, `signals.py`, `urls.py`, `settings.py`, `seed.py`, `tests/helpers.py`, `docs/` | Jhon Emmanuele Alcañices, all members for review |

## 3. Git workflow and records

Repository:
<https://github.com/ehmjhn/Campus_Equipment_Borrowing_and_Inventory_System>

1. `master` always runs and passes tests.
2. Work happens on short branches such as `user-portal-dev`.
3. Commit messages follow `area: imperative summary`.
4. A second member reviews changes that touch workflows or permissions.
5. Pull request #1 merged `user-portal-dev` into `master` after portal review.

Commit history at packaging time:

| Commit | Date | Author | Purpose |
| :--- | :--- | :--- | :--- |
| `9c6e858` | 2026-10-22 | Emman Alcanices | Core schema and dashboard framework |
| `b22862f` | 2026-10-22 | Emman Alcanices | Dashboard and A1–A3 |
| `a657104` | 2026-10-23 | Daniel Alejandrino | A4–A6 equipment workflows |
| `b1f5538` | 2026-10-23 | Copilot (reviewed by Jerome San Pedro) | A7–A8 |
| `0692978` | 2026-10-23 | Jerome San Pedro | A6–A8 |
| `ee361d3` | 2026-10-24 | Emman Alcanices | Custom admin completion and layout architecture |
| `ff17c3f` | 2026-10-24 | Ian Joshua Lizano | Basic-user URL routes |
| `5145c9d` | 2026-10-25 | Marc Renzo Bulaong | U3 and U4 |
| `0ab10f1` | 2026-10-25 | Emman Alcanices | Merge of `user-portal-dev` (PR #1) |

The raw branch graph is stored in `docs/evidence/git_graph.txt`.

## 4. Review checklist

- [x] Does the change enforce the role server-side, not only in the template?
- [x] Is every state-changing endpoint POST-only?
- [x] Is a multi-row workflow wrapped in `transaction.atomic()`?
- [x] Are units locked before their status changes?
- [x] Does the change write a meaningful `AuditLog` entry?
- [x] Are user inputs escaped and validated?
- [x] Is there a test that fails before the change and passes after it?
- [x] Is the feature traceable to a requirement ID?

## 5. Coordination record

Reconstructed from repository history and the group's asynchronous coordination. No
attendee list is invented; each row lists the members whose commits or review work are
visible for that date.

| Date | Participants | Decisions / progress | Follow-up owner |
| :--- | :--- | :--- | :--- |
| 2026-10-22 | Emman, Daniel, Jerome | Agreed on two roles, custom `/manage/` admin, shared models, and requirement mapping A1–A8 / U1–U4 | Emman |
| 2026-10-23 | Daniel, Jerome | Split workflow screens; A4–A6 views merged; A7/A8 dashboard and audit work started | Daniel, Jerome |
| 2026-10-24 | Emman, Ian, Renz | Standardised layout/navigation; portal URL routes prepared on `user-portal-dev` | Emman, Ian |
| 2026-10-25 | Renz, Ian, Emman | U3/U4 completed, reviewed, and merged through PR #1; acceptance scenarios agreed | Renz, Emman |
| 2026-10-28 | All six | Final verification, documentation review, ZIP packaging, and 12-minute rehearsal | Emman, Alexander |

## 6. Individual contribution statements

> **Jhon Emmanuele S. Alcañices:** Built the shared data model, role decorators, A1
> account management, A2 catalog/unit management, A3 review and atomic approval, the
> layout architecture, and the integration/packaging work. The code lives in
> `models.py`, `views.py`, `templates/manage/`, and `tests/test_admin_accounts.py`,
> `tests/test_catalog_units.py`, and `tests/test_requests_release.py`. Verified with the
> full 123-test suite and demonstrated the admin review and inventory flows.

> **Daniel B. Alejandrino:** Built the A4 release workflow, borrowing slip, A5 per-unit
> return handling, and the maintenance routing used by A6. The code lives in
> `views.py` (`release_management`, `issue_approved_request`, `return_management`,
> `record_unit_return`) and `templates/manage/release_management.html`,
> `borrowing_slip.html`, and `return_management.html`. Verified with
> `tests/test_requests_release.py::ReleaseTests` and
> `tests/test_returns_maintenance.py`.

> **Jerome M. San Pedro:** Built and integrated the A6 maintenance close/reconcile
> behaviour, A7 dashboard/report views, and A8 audit/settings page. The code lives in
> `views.py` (`maintenance_management`, `close_maintenance_record`,
> `admin_dashboard`, `dashboard_report_csv`, `overdue_report`,
> `overdue_report_csv`, `audit_settings_management`) and the corresponding manage
> templates. Verified with `tests/test_returns_maintenance.py::MaintenanceTests` and
> `tests/test_reports_settings.py`.

> **Ian Joshua L. Lizano:** Built the basic-user routing and landing-page behaviour and
> reviewed registration/profile access rules. The code lives in `urls.py`,
> `views.portal_home`, `views.role_redirect`, `templates/portal/`, and
> `templates/registration/`. Verified with `tests/test_auth_routing.py` and the portal
> catalog tests.

> **Marc Renzo D. Bulaong:** Built U3 request submission and U4 request history and
> cancellation. The code lives in `views.borrow_request_create`,
> `views.request_history`, `views.cancel_borrow_request`,
> `templates/portal/request_form.html`, and `templates/portal/request_history.html`.
> Verified with `tests/test_portal.py::RequestSubmissionTests` and
> `RequestHistoryTests`, including released reserved units.

> **Alexander A. Azotes:** Contributed the U1/U2 acceptance-test checklist, documentation
> review, and the problem/goals presentation segment; reviewed the catalog and profile
> screens against the privacy requirements. Evidence is recorded in
> `docs/01_user_needs.md`, `docs/04_professional_judgment.md`, and the demonstration
> plan in `docs/06_communication_guides.md`.

## 7. Evidence

- `docs/evidence/git_graph.txt` — branch/commit graph.
- `docs/evidence/tests.txt` — passing suite used for review sign-off.
- Pull request #1: <https://github.com/ehmjhn/Campus_Equipment_Borrowing_and_Inventory_System/pull/1>
- This document contains the individual contribution statements; signed copies can be
  printed from this section if the instructor requires them.
