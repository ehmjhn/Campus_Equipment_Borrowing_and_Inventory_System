# Campus Equipment Borrowing and Inventory System

**Course:** IT 401W Web Programming and Frameworks
**Project:** Final Project A
**Stack:** Python 3.12, Django 6.1.2, Django ORM, server-rendered templates, Bootstrap 5.3.3 (vendored), SQLite

A Django application where campus users request equipment while administrators manage
inventory, approvals, releases, returns, maintenance, and operational reports. Every
physical unit is tracked individually so the same asset can never be issued twice.

> The Django admin interface is intentionally **not** installed or routed. All
> administrative features are custom-coded under `/manage/`.

---

## 1. Quick start

```powershell
# 1. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables (optional for local demo)
Copy-Item .env.example .env
# Edit .env and replace DJANGO_SECRET_KEY with a generated key

# 4. Create the database schema
python manage.py migrate

# 5. Load the fictional demo data (resets existing demo data)
python manage.py seed

# 6. Run the development server
python manage.py runserver
```

Open <http://127.0.0.1:8000/>. The root URL routes each signed-in user to the area
that matches their role.

### Environment variables

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `DJANGO_SECRET_KEY` | development-only fallback | Cryptographic signing key; set a generated value in `.env` |
| `DJANGO_DEBUG` | `1` | Set to `0` to disable debug pages |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost` | Comma-separated host names accepted by Django |

`.env` is git-ignored. Only `.env.example` is committed, so no secret is shipped in
the submission ZIP. Generate a key with:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### Demo credentials

| Role | Username | Password | Landing page |
| :--- | :--- | :--- | :--- |
| Admin | `admin` | `admin123` | `/manage/` |
| Basic user | `user1` … `user8` | `user123` | `/portal/` |

These are fictional demo accounts created by `python manage.py seed`. They are not
committed credentials and must not be reused outside this project.

### Resetting the data

```powershell
python manage.py seed
```

`seed` deletes the demo rows and recreates them. It is safe to run repeatedly and is
the only supported way to rebuild the demo dataset (the SQLite file is not committed).

---

## 2. Roles and routes

Exactly two roles exist: **ADMIN** and **BASIC USER**.

| Area | Route | Purpose |
| :--- | :--- | :--- |
| Auth | `/accounts/login/`, `/accounts/register/`, `/accounts/logout/` | Sign in, self-registration, sign out |
| Admin | `/manage/` | Dashboard cards and charts |
| Admin | `/manage/accounts/` | A1 list/search/activate/deactivate accounts |
| Admin | `/manage/accounts/<id>/` | A1 account details and full borrowing history |
| Admin | `/manage/categories/`, `/manage/catalog-items/` | A2 category and catalog CRUD (archive, never delete) |
| Admin | `/manage/physical-units/` | A2/A6 physical units, filters, retirement, reconciliation |
| Admin | `/manage/requests/` | A3 searchable, date-filtered, paginated review queue with live availability |
| Admin | `/manage/releases/` | A4 release approved requests and print borrowing slips |
| Admin | `/manage/returns/` | A5 partial/full returns, damaged routing, overdue list |
| Admin | `/manage/maintenance/` | A6 open/close maintenance records |
| Admin | `/manage/audit-settings/` | A8 audit log, date filters, system settings |
| Admin | `/manage/reports/equipment-usage.csv` | A7 date-filtered CSV export |
| Admin | `/manage/reports/overdue/`, `/manage/reports/overdue.csv` | A7 overdue loans report and CSV export |
| User | `/portal/` | U2 basic-user landing page with catalog |
| User | `/portal/catalog/` | U2 search active catalog and see serviceable/live availability |
| User | `/portal/requests/new/` | U3 submit a pending request (no auto-reservation) |
| User | `/portal/requests/` | U4 own request history and cancellation |
| User | `/portal/profile/` | U1 edit personal details only |

Role checks are enforced server-side by the `admin_required` and
`basic_user_required` decorators in `Campus_Equipment_Borrowing_and_Inventory_System_APP/views.py`.
Every mutating view is POST-only and CSRF-protected.

---

## 3. Feature checklist

### Admin side (75%)

- [x] A1 Account list, search, pagination, activation/deactivation, per-account
      borrowing history, audit trail
- [x] A2 Category and catalog item CRUD, archive instead of delete, physical unit
      registration, category/item/status filters, condition/acquisition editing,
      retirement and restore
- [x] A3 Searchable, date-filtered, paginated request queue with live availability,
      approve with specific unit reservation, reject with a required reason
- [x] A4 Convert approved requests to issued loans, block invalid issues, revise due
      dates with a reason, printable borrowing slip
- [x] A5 Partial returns per unit, close loan only when every unit is returned,
      damaged/needs-repair units routed to maintenance, overdue calculation
- [x] A6 Maintenance records with problem/action/admin, fixes return units to
      Available, inventory reconciliation panel
- [x] A7 Live dashboard cards and charts, loan report, date-filtered CSV exports,
      dedicated overdue report with its own CSV export
- [x] A8 Audit log (actor, timestamp, action, details) and configurable limits
      (max loan duration, max quantity)

### User side (25%)

- [x] U1 Public registration (basic users only), sign in/out, profile editing;
      role and activation are not editable by the user
- [x] U2 Search active catalog with total serviceable and available quantities;
      archived items are hidden
- [x] U3 Request 1–3 different items with quantities, purpose, and return date,
      validated against the configured limits
- [x] U4 Own request history, partial/full return details, cancel Pending/Approved
      requests and release reserved units

---

## 4. Business rules

| Rule | Implementation |
| :--- | :--- |
| Two roles only | `UserProfile.ROLE_CHOICES`; registration never accepts a posted role |
| 75/25 split | 8 admin feature areas vs. 4 user feature areas |
| No default admin | `django.contrib.admin` is not installed; `admin.py` is intentionally empty |
| Archive, don't delete | Categories/items use `is_archived`; referenced catalog items are `PROTECT`ed |
| No double issuance | Conditional `unique_active_equipment_unit_allocation` constraint plus row locks and transaction blocks |
| Allocation history | `UnitAllocation` rows are kept; returns/cancellations set `released_at` and `release_reason` |
| Unit states | Available, Reserved, Issued, Maintenance, Retired |
| Validation defaults | 7 days maximum duration, 3 units per item (`SystemSetting`) |
| Security | CSRF middleware, password hashing, ORM escaping, ownership filters, role checks |
| Audit | Every sensitive action writes an `AuditLog` row |

### Workflow

```text
Pending ──► Approved ──► Issued ──► Partially Returned ──► Returned
   │            │
   ├──► Rejected│
   └──► Cancelled ◄──┘
```

`Overdue` is computed dynamically from the due date and is never stored as a status.

---

## 5. Project structure

```text
.
├── manage.py
├── requirements.txt
├── README.md
├── docs/                                  # written documentation and defense evidence
├── templates/
│   ├── base.html                          # shared shell, local Bootstrap, CSS/JS layers
│   ├── partials/                          # messages, pagination, empty states, icon sprite
│   ├── registration/                      # login and registration
│   ├── portal/                            # basic-user screens
│   └── manage/                            # custom admin screens
├── static/
│   ├── vendor/bootstrap.min.css           # Bootstrap 5.3.3, served locally
│   ├── css/                               # base, layout, components, pages, responsive, print
│   ├── js/app.js                          # optional progressive enhancement
│   └── img/favicon.svg
├── campus_equipment_borrowing_and_inventory_system/
│   ├── settings.py
│   └── urls.py
└── Campus_Equipment_Borrowing_and_Inventory_System_APP/
    ├── models.py                          # 11 entities and constraints
    ├── forms.py                           # request, profile, registration forms
    ├── views.py                           # all admin and portal logic
    ├── templatetags/ui.py                 # {% icon %} inline-SVG tag
    ├── signals.py                         # profile auto-creation
    ├── migrations/
    ├── management/commands/seed.py        # reproducible demo dataset
    └── tests/                             # requirement-grouped test package
```

---

## 6. Running the tests

```powershell
python manage.py test
```

The suite is organized by requirement area so failures map directly to a feature:

| Test module | Covers |
| :--- | :--- |
| `tests/test_auth_routing.py` | U1 registration and role-aware routing |
| `tests/test_admin_accounts.py` | A1 account management and borrowing history |
| `tests/test_catalog_units.py` | A2 catalog, filters, and physical units |
| `tests/test_requests_release.py` | A3 review/availability and A4 release |
| `tests/test_returns_maintenance.py` | A5 returns, allocation release, and A6 maintenance |
| `tests/test_inventory_rules.py` | Section 7 constraints, protection, reconciliation, reallocation |
| `tests/test_reports_settings.py` | A7 dashboard/overdue reports and A8 audit/settings |
| `tests/test_portal.py` | U2 catalog availability, U3 requests, U4 tracking/cancellation |

Useful checks before submitting:

```powershell
python manage.py makemigrations --check --dry-run
python manage.py check
python manage.py test
```

---

## 7. Seed data coverage

`python manage.py seed` produces at least:

- 3 categories, 6 catalog items, 24 physical units
- 1 admin and 8 basic users
- 22 requests across Pending, Approved, Rejected, Cancelled, Issued,
  Partially Returned, and Returned
- 8 issued loans (including overdue loans)
- 4 maintenance records
- units in all five states: Available, Reserved, Issued, Maintenance, Retired
- audit entries for approval, rejection, release, maintenance, and retirement

---

## 8. Documentation

See [`docs/`](docs/README.md) for the submission evidence folder:

1. User needs
2. System design
3. Technology justification
4. Professional judgment
5. Team collaboration
6. Communication guides

Each document contains a traceability table mapping features to views, templates,
tests, and the responsible team member. Raw verification output is in `docs/evidence/`
(`check.txt`, `makemigrations_check.txt`, `tests.txt`, `seed.txt`, `environment.txt`,
`git_graph.txt`), and seeded screenshots of the principal screens are in
`docs/evidence/screenshots/`.
