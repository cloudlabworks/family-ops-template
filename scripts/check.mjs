// Model checks for the blueprint. Node stdlib plus yaml and ajv (dev dependencies).
// 1. Every required domain has at least one operation, and every operation's x-allowed-roles agrees
//    with model/roles.json (no role on an operation in a domain where the matrix says "none").
// 2. The RequestStatus enum equals model/request-states.json, and every transition names known states.
// 3. The examples validate against the OpenAPI component schemas.
// 4. The request scenarios replay through the reference reducer to their expected final status.
import { readFileSync } from "node:fs";
import { parse } from "yaml";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { reduceRequest } from "./request-reducer.mjs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const spec = parse(read("openapi/openapi.yaml"));
const roles = JSON.parse(read("model/roles.json"));
const states = JSON.parse(read("model/request-states.json"));
const failures = [];
const fail = (m) => failures.push(m);

// 1. Domains and roles
const METHODS = ["get", "put", "post", "patch", "delete"];
const opsByDomain = {};
let opCount = 0;
for (const [path, item] of Object.entries(spec.paths)) {
  for (const m of METHODS) {
    const op = item[m];
    if (!op) continue;
    opCount++;
    const id = op.operationId ?? `${m} ${path}`;
    const domain = op.tags?.[0];
    if (!domain || !roles.domains[domain]) { fail(`${id}: first tag '${domain}' is not a domain in model/roles.json`); continue; }
    (opsByDomain[domain] ??= []).push(id);
    const allowed = op["x-allowed-roles"];
    if (!Array.isArray(allowed) || allowed.length === 0) { fail(`${id}: missing x-allowed-roles`); continue; }
    for (const r of allowed) {
      if (!roles.roles[r]) fail(`${id}: unknown role '${r}'`);
      else if (roles.domains[domain][r] === "none") fail(`${id}: role '${r}' allowed, but roles.json says ${domain}/${r} = none`);
    }
    const sec = (op.security ?? spec.security).map((s) => Object.keys(s)[0]);
    const needs = new Set(allowed.map((r) => roles.roles[r]?.kind));
    if (needs.has("device") && !sec.includes("deviceSession")) fail(`${id}: kiosk allowed but deviceSession not accepted`);
    if (needs.has("service") && !sec.includes("serviceToken")) fail(`${id}: service allowed but serviceToken not accepted`);
    if (needs.has("channel") !== sec.includes("channelSignature")) fail(`${id}: channel-webhook and channelSignature must go together`);
    if (op.operationId === "channelDecision" && (allowed.length !== 1 || allowed[0] !== "channel-webhook")) fail(`${id}: only channel-webhook may call it`);
    if (sec.includes("serviceToken") && /decid/i.test(op.operationId ?? "")) fail(`${id}: a service token must never reach a decision route`);
    if (!needs.has("person") && sec.includes("identitySession")) fail(`${id}: accepts identitySession but no person role is allowed`);
    if (/decideRequest|commandLock|stepUp/.test(op.operationId ?? "") && allowed.some((r) => r !== "parent")) fail(`${id}: must be parent-only`);
  }
}
for (const d of roles.requiredDomains) if (!opsByDomain[d]?.length) fail(`required domain '${d}' has no operations`);
for (const [d, row] of Object.entries(roles.domains)) {
  for (const r of Object.keys(roles.roles)) if (!roles.levels.includes(row[r])) fail(`roles.json ${d}/${r}: level '${row[r]}' unknown`);
}
if (roles.domains.audit.parent !== "read" || Object.entries(roles.domains.audit).some(([r, l]) => r !== "parent" && l !== "none")) fail("audit must be parent read-only");

// 1b. docs/roles.md table matches the matrix
const roleNames = Object.keys(roles.roles);
const docRows = read("docs/roles.md").split("\n").filter((l) => /^\| [a-z-]+ \|/.test(l));
for (const [d, row] of Object.entries(roles.domains)) {
  const line = docRows.find((l) => l.startsWith(`| ${d} |`));
  if (!line) { fail(`docs/roles.md has no row for '${d}'`); continue; }
  const cells = line.split("|").slice(2, -1).map((c) => c.trim());
  roleNames.forEach((r, i) => { if (cells[i] !== row[r]) fail(`docs/roles.md ${d}/${r} = '${cells[i]}', roles.json says '${row[r]}'`); });
}

// 2. State machine
const enumStates = spec.components.schemas.RequestStatus.enum;
if (JSON.stringify([...enumStates].sort()) !== JSON.stringify([...states.states].sort())) fail(`RequestStatus enum ${enumStates} != model states ${states.states}`);
for (const t of states.transitions) for (const s of [t.from, t.to].flat()) if (!states.states.includes(s)) fail(`transition names unknown state '${s}'`);
for (const s of states.terminal) if (states.transitions.some((t) => [t.from].flat().includes(s))) fail(`terminal state '${s}' has an outgoing transition`);

// 3. Examples against component schemas
const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
ajv.addSchema({ $id: "openapi", components: spec.components });
const validate = (schema, data, label) => {
  const v = ajv.getSchema(`openapi#/components/schemas/${schema}`);
  if (!v(data)) fail(`${label} does not match ${schema}: ${ajv.errorsText(v.errors)}`);
};
const family = JSON.parse(read("examples/example-family.json"));
validate("Household", family, "examples/example-family.json");
const memberIds = new Set(family.members.map((m) => m.id));
const parents = family.members.filter((m) => m.role === "parent").map((m) => m.id);
const rules = JSON.parse(read("examples/routing-rules.json"));
validate("RoutingRules", rules, "examples/routing-rules.json");
for (const r of [...rules.rules, rules.default]) for (const d of r.deciders) if (!parents.includes(d)) fail(`routing rule decider '${d}' is not a parent`);
const catalog = JSON.parse(read("examples/app-catalog.json"));
for (const app of catalog.apps) validate("CatalogApp", app, `catalog app ${app.id}`);
for (const o of catalog.optIns ?? []) {
  validate("AppOptIn", o, `opt-in ${o.member}/${o.appId}`);
  if (!memberIds.has(o.member)) fail(`opt-in for unknown member ${o.member}`);
  const app = catalog.apps.find((a) => a.id === o.appId);
  const m = family.members.find((x) => x.id === o.member);
  if (!app) fail(`opt-in for unknown app ${o.appId}`);
  else if (m && !app.ageBands.includes(m.ageBand)) fail(`opt-in ${o.member}/${o.appId}: age band ${m.ageBand} not in ${app.ageBands}`);
  if (m && ["child", "young-child"].includes(m.role) && !parents.includes(o.optedInBy)) fail(`opt-in ${o.member}/${o.appId}: a child's opt-in must be made by a parent`);
}
for (const s of catalog.suggestions ?? []) validate("AppSuggestion", s, `suggestion ${s.id}`);

// 4. Scenarios
const scenarios = JSON.parse(read("examples/request-scenarios.json"));
for (const sc of scenarios.scenarios) {
  validate("Request", sc.request, `scenario '${sc.name}' request`);
  let req = structuredClone(sc.request);
  let lastError = null;
  for (const step of sc.steps) {
    const out = reduceRequest(req, step);
    if (out.error) { lastError = out.error; if (!step.expectError) fail(`scenario '${sc.name}': unexpected refusal '${out.error}' at ${JSON.stringify(step)}`); }
    else { if (step.expectError) fail(`scenario '${sc.name}': expected refusal '${step.expectError}' at ${JSON.stringify(step)}`); req = out.request; }
    if (step.expectError && out.error && out.error !== step.expectError) fail(`scenario '${sc.name}': refusal '${out.error}', expected '${step.expectError}'`);
  }
  if (req.status !== sc.expectStatus) fail(`scenario '${sc.name}': ended '${req.status}', expected '${sc.expectStatus}'`);
  validate("Request", req, `scenario '${sc.name}' final request`);
  void lastError;
}

if (failures.length) {
  console.error(`check: ${failures.length} failure(s)`);
  for (const f of failures) console.error(`- ${f}`);
  process.exit(1);
}
console.log(`check: ok (${opCount} operations across ${Object.keys(opsByDomain).length} domains, ${scenarios.scenarios.length} request scenarios, ${catalog.apps.length} catalog apps)`);
