# 03 — Technology Justification

## 1. Required stack

The brief requires Python, Django, the Django ORM, server-rendered templates,
HTML/CSS/JS, and Bootstrap. SQLite is explicitly allowed for demonstration.

| Layer | Choice | Version | Justification |
| :--- | :--- | :--- | :--- |
| Language | Python | 3.12.10 | Required course language; readable and well supported |
| Framework | Django | 6.1.2 | Authentication, forms, CSRF, ORM, migrations, and test client in one maintained package |
| ORM | Django ORM | bundled | Parameterised queries, relationships, aggregates, and transactions without raw SQL |
| Database | SQLite | bundled | Zero-setup file database suitable for a local demonstration |
| Templates | Django template language | bundled | Server-rendered HTML with inheritance and auto-escaping |
| UI framework | Bootstrap | 5.3 via CDN | Required styling option; no build step or package manager |
| Tests | `django.test.TestCase` | bundled | Exercises views, ORM constraints, permissions, and CSV responses |
| Charts | CSS/HTML progress bars | — | No extra dependency; values are derived from ORM aggregates |

Only one third-party Python package is declared in `requirements.txt`: Django itself.
This keeps setup reproducible and avoids any package that generates an admin UI, which
the specification prohibits.

## 2. Alternatives considered

### Web framework

| Option | Strengths | Why not chosen |
| :--- | :--- | :--- |
| **Django** (chosen) | Batteries included: ORM, auth, forms, CSRF, migrations, test client; fast to build a secure CRUD app | Slightly opinionated structure |
| Flask | Minimal and flexible | Would require hand-building auth, forms, CSRF, and migrations |
| FastAPI | Excellent async API performance | API-first; server-rendered forms would need more glue |
| Laravel / Rails | Mature MVC ecosystems | Course stack is Python/Django |

### Database

| Option | Strengths | Why not chosen |
| :--- | :--- | :--- |
| **SQLite** (chosen) | Zero setup, file-based, sufficient for a demo, bundled with Python | Weak multi-writer concurrency |
| PostgreSQL | Strong concurrency and production-grade features | Requires a server and credentials on every demo machine |
| MySQL | Widely available | Same setup cost as PostgreSQL with no advantage here |

The concurrency requirement is still demonstrated on SQLite through
`transaction.atomic()`, `select_for_update()` (a no-op on SQLite but correct on
production databases), and database uniqueness constraints. The design does not rely
on SQLite-specific behaviour.

### UI approach

| Option | Strengths | Why not chosen |
| :--- | :--- | :--- |
| **Server-rendered templates + Bootstrap CDN** (chosen) | Matches the required stack, accessible HTML semantics, no build step | Full page reloads |
| React/Vue SPA | Rich client interactions | Adds a toolchain and a second codebase outside the course scope |
| Custom CSS framework | Complete design control | Styling is assigned to another member; this repository keeps HTML structure only |

### Emerging technology evaluation: HTMX

HTMX is a small JavaScript library that lets server-rendered HTML issue partial
requests through attributes such as `hx-post` and `hx-target`. It was evaluated as a
possible enhancement for the review queue and dashboard.

| Criterion | Assessment |
| :--- | :--- |
| Effectiveness | Could remove full-page reloads for approval and filtering while keeping Django views authoritative |
| Compatibility | Works with Django templates and CSRF tokens; no separate API layer required |
| Security | The server would still enforce roles, POST-only mutations, and ownership; HTMX itself adds no authentication |
| User needs | Faster review feedback would help administrators, but the current queue already meets the requirement |
| Maintenance | Adds a JavaScript dependency and partial-template conventions that every member must learn |

**Recommendation:** do not adopt HTMX for the submitted version. The requirement is
satisfied with standard forms, the extra dependency would have to be justified in the
submission, and the team's remaining time is better spent on test coverage and
documentation. It is a reasonable future enhancement after the course.

## 3. Why the architecture fits the requirements

| Requirement | Technical response |
| :--- | :--- |
| No default admin | `django.contrib.admin` is not in `INSTALLED_APPS`; no `admin.site.urls` route exists |
| Custom admin | All `/manage/` screens are ordinary Django views with role checks |
| Concurrency | Transactions + row locks + conditional active-allocation constraint |
| Inventory invariant | `EquipmentUnit.STATUS_CHOICES` is the single source of unit states |
| Validation limits | `SystemSetting` keys read by forms and workflow views |
| Security | Django auth, password hashing, CSRF middleware, ORM escaping, ownership filters |
| Audit | `AuditLog` rows written inside the same transaction as the change |
| Reports | ORM aggregation (`Count`, `TruncMonth`) and streaming `HttpResponse` CSV |
| Reusable logic | Role decorators, `_portal_catalog_items`, `_inventory_status_summary`, `_inventory_anomalies`, `_overdue_loan_rows`, and model methods such as `UnitAllocation.release()` |
| Reproducible demo | `python manage.py seed` builds a complete fictional dataset |

## 4. Performance and scale notes

- Dashboard queries use `select_related`, `prefetch_related`, and database
  aggregation rather than Python loops.
- Lists are paginated (10 accounts, requests, account-history rows, or loans; 25 audit
  rows).
- CSV export streams rows through `HttpResponse`.
- The review queue computes availability in one grouped query rather than one query per
  row.
- At campus scale (hundreds of units, thousands of requests), SQLite remains adequate
  for a single-process deployment. A production deployment would switch `DATABASES` to
  PostgreSQL; no model changes are required.

## 5. Configuration and reproducibility

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

Environment variables:

| Variable | Purpose |
| :--- | :--- |
| `DJANGO_SECRET_KEY` | Signing key; replace the development fallback |
| `DJANGO_DEBUG` | `1` for local development, `0` for non-debug runs |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated accepted host names |

`.env` is excluded from Git; `.env.example` is committed. No real credential or
private student record is included in the repository or ZIP.

## 6. Version-control and testing records

The repository is public at
<https://github.com/ehmjhn/Campus_Equipment_Borrowing_and_Inventory_System>. Development
used short-lived branches and pull requests; for example, the portal work was merged
from `user-portal-dev` through pull request #1.

Representative commits:

| Commit | Date | Author | Purpose |
| :--- | :--- | :--- | :--- |
| `9c6e858` | 2026-10-22 | Emman Alcanices | Core schema and dashboard framework |
| `b22862f` | 2026-10-22 | Emman Alcanices | Dashboard and A1–A3 |
| `a657104` | 2026-10-23 | Daniel Alejandrino | A4–A6 equipment workflows |
| `b1f5538` | 2026-10-23 | Copilot | A7–A8 |
| `0692978` | 2026-10-23 | Jerome San Pedro | A6–A8 |
| `ee361d3` | 2026-10-24 | Emman Alcanices | Layout architecture and admin completion |
| `ff17c3f` | 2026-10-24 | Ian Joshua Lizano | Basic-user URL routes |
| `5145c9d` | 2026-10-25 | Marc Renzo Bulaong | U3 and U4 |
| `0ab10f1` | 2026-10-25 | Emman Alcanices | Merge of portal pull request |

### Final measured verification

| Metric | Result |
| :--- | :--- |
| Test count | **123 tests** |
| Test result | **OK** |
| Runtime reported by Django | **246.973 seconds** |
| System check | No issues |
| Migration check | No changes detected |
| Seed command | Completed successfully |
| Machine | 12th Gen Intel Core i5-12450H, 8 cores, 15.7 GB RAM |
| Operating system | Microsoft Windows NT 10.0.26300.0 |
| Python / Django | 3.12.10 / 6.1.2 |

Raw output is stored in `docs/evidence/tests.txt`, `check.txt`,
`makemigrations_check.txt`, `seed.txt`, and `environment.txt`.

## 7. Conclusion

Django with the ORM, server-rendered templates, Bootstrap, and SQLite is the smallest
stack that satisfies every required capability while remaining explainable member by
member. The only reasonable production change is PostgreSQL plus environment-managed
secrets; the application code does not depend on SQLite-specific features.
