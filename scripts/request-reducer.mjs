// Reference reducer for the request state machine (model/request-states.json).
// A server implementation must enforce the same rules; this file is the executable spec the checks replay.
//
// step = { actor, actorRole, action, verdict?, at?,
//          channel-decide only: decider, quickReplyEnabled, signatureValid, senderMatches, nonceValid, nonceVerdict }
// action: open | decide | channel-decide | answer | cancel | complete | expire
// Returns { request } or { error } with the refusal code a server would return.

const FINAL = new Set(["declined", "done", "expired", "cancelled"]);
const DECIDABLE = new Set(["new", "seen"]);

export function reduceRequest(req, step) {
  const r = structuredClone(req);
  const at = step.at ?? "2030-01-01T00:00:00Z";
  if (r.hiddenFrom?.includes(step.actor)) return { error: "not-found" };

  switch (step.action) {
    case "open":
      if (r.deciders.includes(step.actor) && r.status === "new") r.status = "seen";
      return { request: r };

    case "channel-decide":
      // Opt-in quick reply. Only the platform's signed callback reaches this path; household services never do.
      if (step.actorRole !== "channel-webhook") return { error: "forbidden" };
      if (!step.quickReplyEnabled) return { error: "quick-reply-off" };
      if (!step.signatureValid) return { error: "signature-invalid" };
      if (!step.senderMatches) return { error: "sender-mismatch" };
      if (!step.nonceValid) return { error: "nonce-invalid" };
      if (step.nonceVerdict !== step.verdict) return { error: "nonce-verdict-mismatch" };
      return decide(r, step.decider, step.verdict, "channel", at);

    case "decide":
      if (step.actorRole !== "parent") return { error: "forbidden" };
      return decide(r, step.actor, step.verdict, "session", at);

    case "answer":
      if (step.actor !== r.requester) return { error: "forbidden" };
      if (r.status !== "needs_info") return { error: "illegal-transition" };
      r.status = "seen";
      return { request: r };

    case "cancel":
      if (step.actor !== r.requester) return { error: "forbidden" };
      if (FINAL.has(r.status) || r.status === "approved") return { error: "illegal-transition" };
      r.status = "cancelled";
      return { request: r };

    case "complete":
      if (step.actor !== r.requester && !r.deciders.includes(step.actor)) return { error: "forbidden" };
      if (r.status !== "approved") return { error: "illegal-transition" };
      r.status = "done";
      return { request: r };

    case "expire":
      if (!["new", "seen", "needs_info"].includes(r.status)) return { error: "illegal-transition" };
      r.status = "expired";
      return { request: r };

    default:
      return { error: "unknown-action" };
  }
}

function decide(r, decider, verdict, via, at) {
  if (!r.deciders.includes(decider)) return { error: "not-a-decider" };
  if (decider === r.requester) return { error: "own-request" };
  if (!DECIDABLE.has(r.status)) return { error: "illegal-transition" };
  if (r.decisions.some((d) => d.decider === decider && d.verdict !== "needs_info")) return { error: "already-decided" };
  r.decisions.push({ decider, verdict, at, via });
  r.revision += 1;
  if (verdict === "needs_info") { r.status = "needs_info"; return { request: r }; }
  if (verdict === "decline") { r.status = "declined"; return { request: r }; }
  // approve
  if (r.policy === "either") { r.status = "approved"; return { request: r }; }
  const approvedBy = new Set(r.decisions.filter((d) => d.verdict === "approve").map((d) => d.decider));
  r.status = r.deciders.every((d) => approvedBy.has(d)) ? "approved" : "seen";
  return { request: r };
}
