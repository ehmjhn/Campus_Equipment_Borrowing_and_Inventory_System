# Submission Documentation

This folder is the documentation/evidence package required by the Final Project A
brief (section 8). Each file covers one required category.

| # | Document | Required category |
| :-- | :--- | :--- |
| 01 | [User needs](01_user_needs.md) | User Needs |
| 02 | [System design](02_system_design.md) | System Design |
| 03 | [Technology justification](03_tech_justification.md) | Tech Justification |
| 04 | [Professional judgment](04_professional_judgment.md) | Professional Judgment |
| 05 | [Team collaboration](05_team_collaboration.md) | Team Collaboration |
| 06 | [Communication guides](06_communication_guides.md) | Communication Guides |

The submission is `IT401W_ProjectA_Section_Group.zip`. The environment-specific
section/group token is documented in the title page of the project brief
(**BSIT 4F-G1**) and can be substituted in the ZIP name if the instructor requires the
literal section string.

---

## Traceability map

Use this table during the defense to jump from a requirement to the code that
implements it and the test that proves it.

| Requirement | Views (`views.py`) | Templates (`templates/`) | Tests (`tests/`) |
| :--- | :--- | :--- | :--- |
| A1 Account management | `account_management`, `account_detail`, `toggle_account_status` | `manage/accounts.html`, `manage/account_detail.html` | `test_admin_accounts.py` |
| A2 Catalog & units | `category_*`, `catalog_item_*`, `equipment_unit_*`, `physical_units_management` | `manage/categories.html`, `manage/catalog_items.html`, `manage/physical_units.html` | `test_catalog_units.py` |
| A3 Request review | `request_review`, `request_approve`, `request_reject` | `manage/request_review.html` | `test_requests_release.py::RequestReviewTests` |
| A4 Equipment release | `release_management`, `issue_approved_request`, `revise_approved_due_date`, `borrowing_slip` | `manage/release_management.html`, `manage/borrowing_slip.html` | `test_requests_release.py::ReleaseTests` |
| A5 Returns & overdue | `return_management`, `record_unit_return` | `manage/return_management.html` | `test_returns_maintenance.py::ReturnRecordingTests` |
| A6 Maintenance | `maintenance_management`, `open_maintenance_record`, `close_maintenance_record`, `reconcile_inventory` | `manage/maintenance_management.html`, `manage/physical_units.html` | `test_returns_maintenance.py::MaintenanceTests`, `test_inventory_rules.py::ReconciliationTests` |
| A7 Dashboard & reports | `admin_dashboard`, `dashboard_report_csv`, `overdue_report`, `overdue_report_csv` | `manage/dashboard.html`, `manage/overdue_report.html` | `test_reports_settings.py::DashboardAndSettingsTests`, `OverdueReportTests` |
| A8 Audit & settings | `audit_settings_management` | `manage/audit_settings.html` | `test_reports_settings.py::AuditLogTests` |
| U1 Account & profile | `register`, `profile_view`, `role_redirect`, `portal_home` | `registration/register.html`, `registration/login.html`, `portal/profile.html` | `test_auth_routing.py`, `test_portal.py::ProfileAndAccessTests` |
| U2 Browse equipment | `browse_catalog`, `_portal_catalog_items` | `portal/catalog.html` | `test_portal.py::CatalogTests` |
| U3 Submit request | `borrow_request_create` | `portal/request_form.html` | `test_portal.py::RequestSubmissionTests` |
| U4 Track & cancel | `request_history`, `cancel_borrow_request` | `portal/request_history.html` | `test_portal.py::RequestHistoryTests` |
| Section 7 constraints | `models.py`, migrations `0001`–`0003` | — | `test_inventory_rules.py::ConstraintTests` |
| Allocation history / re-borrowing | `UnitAllocation.release`, approval/return/cancel filters | `manage/account_detail.html`, `manage/request_review.html` | `test_inventory_rules.py`, `test_requests_release.py`, `test_returns_maintenance.py` |
| Profile bootstrap | `signals.py`, `apps.py` | — | `test_auth_routing.py` |
| Demo dataset | `management/commands/seed.py` | — | verified with `manage.py seed` |

## Module ownership

| Member | Primary modules | Secondary / review |
| :--- | :--- | :--- |
| Jhon Emmanuele S. Alcañices (2023100224) | A1 accounts, A2 catalog/units, A3 review, shared foundation, layouts, packaging | Integration and release checks |
| Daniel B. Alejandrino (2023104581) | A4 release, A5 returns, A6 maintenance integration | Release and return review |
| Alexander A. Azotes (2023105498) | U1/U2 acceptance testing, documentation, presentation | Privacy and catalog review |
| Marc Renzo D. Bulaong (2023100233) | U3 submission, U4 tracking/cancellation | Portal test review |
| Ian Joshua L. Lizano (2023103575) | Basic-user routing/landing, U1 registration/profile review | Portal review |
| Jerome M. San Pedro (2023100179) | A6 maintenance, A7 reports, A8 audit/settings | Audit and report review |

The ownership table is the group's submitted plan; `docs/05_team_collaboration.md`
records the corresponding commit history.

---

## Defense checklist

- [x] Every table row above has a live route to demonstrate.
- [x] `python manage.py test` passes on a clean database — 123 tests, OK.
- [x] `python manage.py makemigrations --check --dry-run` reports no changes.
- [x] `python manage.py check` reports no issues.
- [x] Demo accounts sign in and land on the correct role area.
- [x] Seed data shows every workflow status and every unit state.
- [x] Documentation placeholders are replaced with implementation facts.
- [x] Screenshots of the principal admin and basic-user screens are in
      `docs/evidence/screenshots/`.
- [x] Automated WCAG A/AA and layout audits pass; results are recorded in
      `docs/evidence/accessibility.txt`.
- [x] ZIP excludes `.venv/`, `__pycache__/`, `db.sqlite3`, `.env`, and `.idea/`.
