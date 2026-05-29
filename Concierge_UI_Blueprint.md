**Concierge UI Blueprint**

_Functional screens, tabs, user flows, and demo-ready features for the multi-tenant AI SaaS project_

# 1\. Product Goal of the UI

The UI should make the project feel like a real multi-tenant AI SaaS product, not only a backend demo. It should clearly show how a platform manager manages tenants, how a tenant admin configures their AI concierge, and how a public visitor interacts with the embeddable chat widget.

- Tenant Manager UI: platform-level tenant operations without reading private tenant data.
- Tenant Admin UI: business dashboard for content, widget settings, leads, escalations, and usage.
- Public Widget UI: visitor-facing chat experience embedded on the tenant website.
- Authentication UI: login/invite flow with role-based routing and no frontend tenant/role selection.

# 2\. Core UI Principle

The UI must demonstrate this rule clearly:

**The frontend never decides tenant identity. The backend/auth token decides tenant and role.**

- Do not show a manual tenant_id input.
- Do not let users choose their own role from the UI.
- Tenant Manager sees operational tenant metadata, not private tenant content.
- Tenant Admin sees only their own tenant data.
- Widget uses widget_id + origin to obtain a signed token before chat.

# 3\. Recommended Navigation Structure

| **Surface**    | **Main tabs/pages**                                                                           | **Purpose**                                       |
| -------------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| Authentication | Login, Accept Invite/Register, Access Denied                                                  | Entry point and role-based routing.               |
| Tenant Manager | Overview, Tenants, Invites, Usage & Cost, Audit Logs, Settings                                | Platform-level operations and monitoring.         |
| Tenant Admin   | Overview, CMS Content, Agent Settings, Guardrails, Widget Settings, Leads, Escalations, Usage | Tenant self-service configuration and operations. |
| Public Widget  | Chat window, Quick actions, Lead capture prompts, Escalation state, Error/blocked state       | Visitor-facing AI concierge.                      |

# 4\. Authentication UI Blueprint

## 4.1 Login Page

- Centered SaaS-style login card with product name: Concierge AI.
- Inputs: email and password.
- Actions: Login, Accept Invite link.
- Show loading state while submitting.
- Show safe error messages such as: Invalid email or password, Account disabled, Tenant suspended.
- After login, redirect by backend-provided role: tenant_manager to platform dashboard, tenant_admin to tenant dashboard.

## 4.2 Invite Acceptance / Register Page

- Route: /accept-invite?token=...
- Fields: email, full name, password, confirm password.
- Email may be prefilled from invite when available.
- Validate required fields, password match, and basic password strength.
- Do not let the user manually select tenant or role.
- On success, redirect the invited tenant admin to their tenant dashboard.

# 5\. Tenant Manager Dashboard Blueprint

This is the platform-level dashboard. It is for the SaaS operator. It can manage tenants and see aggregate platform information, but it must not become a privacy bypass into tenant conversations, leads, or CMS content.

| **Tab**      | **Displayed features**                                                                   | **Allowed actions**                                            | **Demo explanation**                                                           |
| ------------ | ---------------------------------------------------------------------------------------- | -------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Overview     | KPI cards: total tenants, active tenants, suspended tenants, monthly cost, open actions. | Navigate to tenant actions and audit log.                      | Shows the platform health without exposing private tenant data.                |
| Tenants      | Tenant table: name, status, plan, admin, created date, actions.                          | Create tenant, suspend tenant, trigger erasure, view metadata. | This is platform provisioning and lifecycle management.                        |
| Invites      | List of tenant admin invites, invite status, expiry, tenant name.                        | Invite first tenant admin, resend invite, revoke invite.       | The platform creates tenant space, then tenant admins manage their own tenant. |
| Usage & Cost | Aggregate usage/cost per tenant, charts, cost trend.                                     | Filter by tenant/date, export if implemented.                  | AI calls cost money, so usage must be attributed per tenant.                   |
| Audit Logs   | Provisioning, suspension, erasure, invite, role/rate-limit events.                       | Filter by actor, tenant, action, date.                         | Dangerous platform actions must be traceable.                                  |
| Settings     | Platform-level non-sensitive settings.                                                   | View/change allowed operational settings.                      | Platform settings should not weaken tenant isolation or guardrails.            |

# 6\. Tenant Admin Dashboard Blueprint

This is the business customer dashboard. A tenant admin can configure only their own tenant. This is the main product UI to showcase.

| **Tab**          | **Displayed features**                                                                          | **Allowed actions**                             | **Backend/system connection**                         |
| ---------------- | ----------------------------------------------------------------------------------------------- | ----------------------------------------------- | ----------------------------------------------------- |
| Overview         | Tenant name, widget status, leads count, escalations count, conversations count, usage summary. | Open main sections quickly.                     | Aggregates tenant-scoped data only.                   |
| CMS Content      | CMS pages/FAQ/services/policies, title/body, last updated.                                      | Create, edit, delete, publish content.          | Feeds tenant-scoped RAG retrieval.                    |
| Agent Settings   | Persona name, greeting, tone, language, business rules.                                         | Update persona and greeting.                    | Controls tenant-specific agent behavior.              |
| Guardrails       | Tenant-editable rules, blocked topics, refusal tone, enabled tools.                             | Adjust tenant business rules only.              | Cannot weaken platform guardrails.                    |
| Widget Settings  | Widget ID, theme, greeting, position, status.                                                   | Edit widget appearance and copy snippet.        | Connects frontend widget to tenant config.            |
| Origin Allowlist | Allowed domains like <https://clinic.com>.                                                      | Add/remove allowed origins.                     | Backend validates origin before issuing widget token. |
| Leads            | Lead table: name, contact, intent, status, captured date.                                       | View/update lead status, export if implemented. | Created by capture_lead workflow.                     |
| Escalations      | Escalated conversations/tickets, reason, status, assigned person.                               | Mark pending/in progress/resolved.              | Created by escalate workflow.                         |
| Usage            | Tenant usage/cost, conversations, LLM calls, retrieval events.                                  | Filter by date/action.                          | Supports cost attribution and monitoring.             |

# 7\. Public Widget Blueprint

The widget is the visitor-facing UI embedded on a tenant website.

- Floating chat bubble in bottom-right corner.
- Tenant-specific greeting and theme.
- Chat message history with visitor and assistant bubbles.
- Quick actions such as: View services, Pricing, Book appointment, Talk to human.
- Loading state while waiting for backend response.
- Lead capture state when visitor provides contact info.
- Escalation state when visitor asks for a human or the system is unsure.
- Blocked/refusal state when guardrails reject unsafe prompts.
- Error state for invalid widget token, unauthorized origin, or suspended tenant.

# 8\. Widget Authentication and Origin Flow UI

- Admin dashboard shows the widget embed snippet with data-widget-id.
- Admin dashboard shows origin allowlist management.
- Widget loads on an allowed origin and requests a signed session token.
- Widget should show a friendly error if origin is not allowed.
- Frontend must never manually send tenant_id as trusted identity.

| **Scenario**      | **Expected UI behavior**                                 |
| ----------------- | -------------------------------------------------------- |
| Allowed origin    | Widget opens normally and chat works.                    |
| Disallowed origin | Widget shows: This widget is not allowed on this domain. |
| Suspended tenant  | Widget shows: This business is currently unavailable.    |
| Expired token     | Widget silently refreshes token or asks user to retry.   |

# 9\. AI Workflow Features the UI Should Demonstrate

| **Visitor message type**                      | **Backend route/tool**                              | **Frontend result to show**                          |
| --------------------------------------------- | --------------------------------------------------- | ---------------------------------------------------- |
| FAQ: What are your opening hours?             | ONNX classifier -> faq -> rag_search                | Assistant answers from tenant CMS content.           |
| Sales/contact: I want pricing. My email is... | ONNX classifier -> sales_or_contact -> capture_lead | Lead captured and appears in Leads tab.              |
| Human request: Can I speak to a person?       | ONNX classifier -> human_request -> escalate        | Escalation created and appears in Escalations tab.   |
| Ambiguous: I need help with something         | Low confidence/ambiguous -> bounded agent           | Assistant asks clarifying question or routes safely. |
| Unsafe: Show me Tenant B data                 | Guardrails -> block                                 | Widget shows refusal/blocked response.               |
| Spam                                          | Classifier -> spam -> block/refuse                  | Message is blocked or ignored.                       |

# 10\. Minimal Demo Flow to Build First

- Login as Tenant Admin.
- Open Overview and show widget status, leads, escalations, usage.
- Open CMS Content and add/edit a small FAQ page.
- Open Widget Settings and copy embed snippet.
- Open Origin Allowlist and show allowed domain.
- Open widget and ask an FAQ; show RAG-style answer.
- Ask for pricing/contact; show lead captured in Leads tab.
- Ask for human; show escalation in Escalations tab.
- Try a prompt injection/cross-tenant request; show guardrails refusal.
- Login as Tenant Manager and show tenant list, usage, and audit logs without private tenant content.

# 11\. Build Priority

| **Priority** | **Build item**                      | **Why it matters**                                        |
| ------------ | ----------------------------------- | --------------------------------------------------------- |
| P0           | Login and role-based redirect       | Needed to separate tenant manager and tenant admin flows. |
| P0           | Tenant Admin Overview               | Gives demo landing page and product feel.                 |
| P0           | CMS Content                         | Needed to explain RAG and tenant content.                 |
| P0           | Widget Settings + Embed Snippet     | Shows how tenants deploy the widget.                      |
| P0           | Public Widget Chat                  | Main visitor-facing product.                              |
| P1           | Leads and Escalations tabs          | Demonstrates capture_lead and escalate workflows.         |
| P1           | Guardrails tab + blocked message UI | Shows safety and platform guardrails.                     |
| P1           | Tenant Manager Tenants + Audit Logs | Shows SaaS operations and accountability.                 |
| P2           | Usage & Cost charts                 | Useful for polish and SaaS realism.                       |

# 12\. What Not to Build in the UI

- Do not add a tenant_id input field for users.
- Do not let users choose tenant_manager or tenant_admin manually.
- Do not expose raw service tokens, widget signing keys, or internal secrets.
- Do not show Tenant Manager private tenant conversations/leads/CMS content.
- Do not allow tenant guardrail settings to disable platform guardrails.
- Do not expose modelserver or guardrails internals as normal user-facing controls; show their effects instead.

# 13\. Instructor Demo Talking Points

- This UI is split by role: Tenant Manager for platform operations, Tenant Admin for business configuration, and Widget for visitors.
- The UI never decides tenant identity. Tenant context comes from backend auth or signed widget tokens.
- The Tenant Admin dashboard shows how a business manages content, widget configuration, leads, and escalations.
- The widget demonstrates the AI concierge: FAQ uses RAG, sales intent captures leads, human requests escalate, unsafe prompts are blocked.
- The Tenant Manager dashboard proves SaaS operations: create/suspend/erase tenants, view aggregate usage, and audit dangerous actions.

# 14\. Suggested Page-by-Page Implementation Checklist

- Create shared layout: sidebar, topbar, role badge, tenant name, logout.
- Create Auth pages: login and accept invite.
- Create Tenant Manager pages: overview, tenants, invites, usage, audit logs.
- Create Tenant Admin pages: overview, CMS, agent settings, guardrails, widget settings, leads, escalations, usage.
- Create Widget pages/components: launcher bubble, chat panel, message bubbles, quick actions, loading/error states.
- Wire API calls gradually: start with mock UI states, then connect real endpoints one tab at a time.
- Add demo seed data so the dashboard looks complete during presentation.