// Generic privacy scan for a public household blueprint. Fails on anything that looks like real
// household data: IP addresses, email addresses (other than placeholders), phone numbers, street
// addresses, dates of birth, and private-network hostnames. Keep your own family-specific deny list
// OUTSIDE this repository and run it locally before every push (see docs/implementation-guide.md);
// a public deny list of real names would itself be the leak.
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

const files = execFileSync("git", ["ls-files", "--cached", "--others", "--exclude-standard"], { encoding: "utf8" })
  .split("\n")
  .filter((f) => f && !f.startsWith("node_modules/") && f !== "package-lock.json");

const ALLOWED_EMAIL = /^(?:[0-9]+\+)?cloudlabworks@users\.noreply\.github\.com$|@example\.(?:com|org|invalid)$/i;
const CHECKS = [
  ["ipv4 address", /\b(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}\b/g, (m) => !/^0\.0\.0\.0$/.test(m)],
  ["email address", /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, (m) => !ALLOWED_EMAIL.test(m)],
  ["phone number", /(?:\+?1[ .-]?)?\(?\b[2-9]\d{2}\)?[ .-]\d{3}[ .-]\d{4}\b/g, () => true],
  ["street address", /\b\d{2,6}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+(?:Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Drive|Dr|Court|Ct|Way|Boulevard|Blvd)\b\.?/g, () => true],
  ["date of birth", /\b(?:dob|date of birth|born)\b[^\n]{0,20}\b(?:19|20)\d\d-\d\d-\d\d\b/gi, () => true],
  ["private hostname", /\b[a-z0-9-]+\.(?:lan|lab|home|internal|localdomain)\b/gi, (m) => !/^(?:example|your-home)\./i.test(m)],
  ["private key", /-----BEGIN [A-Z ]*PRIVATE KEY-----/g, () => true],
];

const hits = [];
for (const f of files) {
  let text;
  try { text = readFileSync(f, "utf8"); } catch { continue; }
  text.split("\n").forEach((line, i) => {
    for (const [label, re, keep] of CHECKS) {
      for (const m of line.matchAll(re)) if (keep(m[0])) hits.push(`${f}:${i + 1}: ${label}: ${m[0]}`);
    }
  });
}
if (hits.length) {
  console.error(`privacy-scan: ${hits.length} finding(s)`);
  for (const h of hits) console.error(`- ${h}`);
  process.exit(1);
}
console.log(`privacy-scan: ok (${files.length} files)`);
