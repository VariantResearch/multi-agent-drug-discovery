# Security model

MADD is a single-operator research tool. This document states what
the console and the pipeline defend against, what they deliberately
do not, and where the load-bearing controls sit, so nobody has to
guess.

## Trust boundaries

- **The operator** (whoever runs the console) is trusted. The
  console has no accounts or login of its own: it binds to loopback,
  and remote access is expected to arrive through an authenticating
  tunnel (the deployment on record is Cloudflare Access in front of
  a tunnel to the loopback port). Anyone who can reach the port as
  the operator can start runs that spend the operator's API budget.
- **Model output is untrusted.** Every provider response is parsed
  against a strict contract; unparseable or schema-failing output
  becomes a failure record that contributes nothing, never a
  repaired approximation.
- **Source text is untrusted.** Papers, registry records, and trial
  listings are data an attacker could poison (a crafted abstract is
  a realistic prompt-injection vehicle), so they are fenced as data
  in every prompt (see below) and, more importantly, no claim
  survives on a model's say-so: identifiers must resolve, quotes
  must appear verbatim in retrieved full text, and judged checks
  can only strike or flag, never create support.
- **Run bundles are untrusted input to the console.** Bundles are
  files; the console renders their contents into pages, so every
  value is escaped for both text and attribute contexts in the page
  script, and the standalone HTML reports escape with html.escape.

## Console defences

- **Host allowlist.** Requests are answered only for `localhost`,
  `127.0.0.1`, `::1`, and the deployment's one tunnelled hostname.
  Any other Host is refused before routing, which is the
  DNS-rebinding defence: a public name resolving to 127.0.0.1 still
  arrives with that public name as Host.
- **Origin check on POSTs.** A POST carrying an Origin or Referer
  naming any other host is refused (CSRF and cross-site driving of
  the API). Browsers always send Origin on cross-site POSTs;
  non-browser clients send neither and rely on the Host check.
- **Body cap.** POST bodies are capped at 1 MiB and refused unread
  past it; a malformed or negative Content-Length is a 400, not a
  crashed handler.
- **Response headers.** Every response carries
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and
  `Referrer-Policy: no-referrer`. HTML responses also carry a
  Content-Security-Policy matching the console's actual shape
  (same-origin scripts plus the page's inline script and styles,
  `frame-ancestors 'none'`, `form-action 'self'`).
- **Path discipline.** Run ids are validated before any file read
  (separators and dot segments refused), and vendored assets are
  served from a fixed whitelist. API keys are never stored or
  returned: setup records environment variable NAMES, and the API
  reports only whether each variable is present.

## Prompt-injection posture

Fencing is the visible layer: the research system prompt carries a
data-boundary rule, the frame travels between explicit DATA
markers, and the entailment, contradiction, tournament,
meta-review, and design prompts each state that the material shown
is data, never instructions, including when that material imitates
an instruction.

Fencing is not the load-bearing layer, and this project does not
pretend otherwise: a determined injection can still try to steer
which real claims a model emphasises. What it cannot do is mint
evidence. A claim needs a real identifier that resolves, a quote
that checks verbatim against retrieved full text, and survival
through judges whose verdict vocabularies are closed and parsed
strictly; the consensus and audit machinery treats unsupported
output as failure, not as content to be repaired. Injection that
only persuades still faces the same mechanical audit as honest
error.

## Deliberate non-goals

- No authentication or TLS in the console process itself; those
  belong to the tunnel and identity layer in front of it.
- No sandboxing of provider traffic beyond the recorded endpoints
  and the budget machinery; a configured provider base URL is the
  operator's own choice.
- Frozen bundles are integrity-hashed for tamper evidence, not
  encrypted; protect the runs directory as you would any research
  record.
