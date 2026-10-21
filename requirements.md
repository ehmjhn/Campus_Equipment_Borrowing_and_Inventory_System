# IT 401W - Final Project A: Campus Equipment Borrowing and Inventory System

**Course:** IT 401W Web Programming and Frameworks (1st Sem 2026-2027)
**Instructor:** Dr. Aaron Paul M. Dela Rosa
**Group Size:** 5–6 members
**Demonstration:** Week 17 (12-minute demo + 3-minute Q&A)

---

## 1. Project Overview
Build a Python Django application that allows campus users to request equipment while administrators manage inventory, approval, release, return, maintenance, and operational reports. 
*   **Core Goal:** Maintain an accurate history of each physical unit and prevent equipment from being issued twice.
*   **Workload Distribution:** ~75% Custom Admin Side, ~25% Basic User Side.
*   **Restriction:** The use of Django's default admin interface (`admin.site.urls`) or any packages that auto-generate the admin interface is **strictly prohibited**. The admin side must be completely custom-coded.

## 2. Learning Targets
| Course Outcome (CO) | Project Evidence | Target PO |
| :--- | :--- | :--- |
| **CO1** | Python and Django backend components | PO-g |
| **CO2** | User requirements and MTV design with options comparison | PO-d |
| **CO3** | Functional application and tests | PO-e |
| **CO4** | Secure data handling and justified privacy/access decisions | PO-n |
| **CO5** | ORM relationships queries and reusable modules/libraries | PO-g |
| **CO6** | Individual contribution documentation and defense | PO-h, PO-j |

## 3. User Roles
Exactly two user levels are permitted (no third roles like staff or supervisor allowed):
1.  **ADMIN:** Handled via `/manage/` routes.
2.  **BASIC USER:** Handled via `/portal/` routes.

---

## 4. Custom Admin Requirements (Admin Role)
Every protected server-side action must enforce the admin role.
*   **A1 Account Management:** List, search, activate, deactivate user accounts. Deactivation blocks sign-ins but keeps records. Admins cannot be registered via public registration.
*   **A2 Equipment Catalog:** CRUD operations for categories and items. Register specific physical units (asset codes, condition, acquisition date). *Archive* records instead of deleting to preserve transaction history.
*   **A3 Request Review:** Searchable/paginated queue. Review and approve/reject requests with reasons. Allocate specific physical units upon approval to reserve them.
*   **A4 Equipment Release:** Convert approved requests to issued loans. Record release date/admin. Print borrowing slip. Prevent invalid issues (cancelled, already issued, insufficient units).
*   **A5 Returns & Overdue:** Support partial returns per physical unit. Close loan only when all units are returned. Route damaged units to maintenance.
*   **A6 Maintenance:** Manage records (problem, action, admin). Fixes return units to "Available". Reconcile unit counts.
*   **A7 Dashboard & Reports:** Live cards (available units, pending requests, active/overdue loans). Charts (monthly issued, category usage). Date-filtered CSV export reports. Must use live database data.
*   **A8 Audit & Settings:** Audit log tracking all actions (actor, timestamp, action). Manage settings (max loan duration, max quantity).

---

## 5. Basic User Requirements (Basic User Role)
*   **U1 Account/Profile:** Register, sign in/out, edit personal details. Role/activation status are uneditable.
*   **U2 Browse Equipment:** Search active catalog, view descriptions and currently *available* quantities. Cannot see internal notes or audit records.
*   **U3 Submit Request:** Request 1-3 different items, quantities, purpose, return date. Validates against limits. Submission creates a *Pending* request (does not auto-reserve units).
*   **U4 Track & Cancel:** View own history. Cancel Pending or Approved requests (frees up units). Cannot alter due dates or issue states.

---

## 6. Database and Workflow
### Minimum Entities
*   **User/Profile:** Django Auth identity, role, contact, activation.
*   **Category & CatalogItem:** Hierarchical item grouping, active/archive flags.
*   **EquipmentUnit:** Unique asset code, condition, status.
*   **BorrowRequest & RequestItem:** Owner, dates, workflow status.
*   **UnitAllocation:** Tracks unit reservations to prevent simultaneous active allocations.
*   **Loan & ReturnRecord:** Issued loans and individual unit returns.
*   **MaintenanceRecord:** Repair tracking.
*   **AuditLog & SystemSetting:** System configurations and action tracking.

### Required Workflow
*   `Pending` → `Approved` / `Rejected` / `Cancelled`
*   `Approved` → `Issued` / `Cancelled`
*   `Issued` → `Partially Returned` / `Returned`
*   `Partially Returned` → `Returned`
*   *(Note: `Overdue` is a dynamically calculated state, not a manual status).*

### Seed Data Minimums
3 categories, 6 catalog items, 18 physical units, 1 admin, 8 basic users, 20 requests, 8 issued loans, 4 maintenance records. Must include rejected/cancelled requests, partial/damaged returns, and overdue loans. Use fictional data.

---

## 7. Business & Technical Rules
*   **Concurrency:** Use database transactions and locking/constraints for allocation. (e.g., Two admins approving the last unit simultaneously must result in only one success).
*   **Inventory Invariant:** Units must strictly be in one of these states: Available, Reserved, Issued, Maintenance, or Retired.
*   **Validation:** Default settings: Max 7 days duration, max 3 units per item.
*   **Tech Stack:** Python, Django, Django ORM, server-rendered templates, HTML/CSS/JS, Bootstrap. SQLite allowed, PostgreSQL/MySQL optional. 
*   **Security:** Enforce object ownership, CSRF protection, hash passwords, escape user content. No unrestricted CRUD.

---

## 8. Submission Package
**File Naming:** `IT401W_ProjectA_Section_Group.zip`
**Contents:**
*   Source Code & Migrations
*   `requirements.txt`
*   `README.md` (with setup instructions)
*   Fixture/Seed command
*   Documentation/Evidence Folder (User Needs, System Design, Tech Justification, Professional Judgment, Team Collaboration, Communication Guides).
*   *Exclude:* Virtual environments, caches, real credentials.
*   Provide safe demo credentials to the instructor.

## 9. Grading Basis
Evaluated individually and as a team using BSIT Universal PO Rubrics: PO-d, PO-e, PO-g, PO-h, PO-j, and PO-n based on the code, documentation, presentation, and Q&A.