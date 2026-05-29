// Owner: Amer
// Console-only widget telemetry with field-level redaction.
//
// Anything resembling a credential is replaced with "[redacted]" before the
// event reaches the console. The redaction list is intentionally small and
// case-insensitive: token, email, password (and obvious aliases).

const REDACT_PATTERN = /^(token|access_token|id_token|refresh_token|email|password)$/i;

function redact(props: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(props)) {
    if (REDACT_PATTERN.test(key)) {
      out[key] = "[redacted]";
    } else if (value && typeof value === "object" && !Array.isArray(value)) {
      out[key] = redact(value as Record<string, unknown>);
    } else {
      out[key] = value;
    }
  }
  return out;
}

export function emit(name: string, props: Record<string, unknown> = {}): void {
  try {
    // eslint-disable-next-line no-console
    console.info(`[concierge.widget.telemetry] ${name}`, redact(props));
  } catch {
    // Telemetry must never throw.
  }
}
