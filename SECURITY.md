## Ayoub — Modelserver, Guardrails, Redaction, and Service Security

### 1. Security Scope

Owner C is responsible for the security layer around:

- classifier modelserver
- guardrails sidecar
- redaction
- service-to-service authentication
- tracing safety
- red-team and redaction evals

This work supports the main Concierge security goal:

> Tenant A must never access Tenant B data, prompts, conversations, leads, vectors, traces, or private configuration.

---

### 2. Service-to-Service Authentication

Internal services must authenticate each other.

The project does not rely on Docker networking as authentication. Even if services are running inside the same Docker Compose network, each protected internal endpoint still requires a Bearer token.

Protected internal endpoints:

| Service | Endpoint | Auth Required |
|---|---|---|
| Modelserver | `POST /predict` | Yes |
| Guardrails | `POST /check` | Yes |

The shared helper is:

```text
app/infra/service_auth.py