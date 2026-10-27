# VitalDock development instructions

- Product purpose: obtain user-authorized wearable data and make it traceable and
  useful to personal agents. Huawei first; keep the common model vendor-neutral.
- Never add real health exports, raw vaults, credentials, locations or screenshots
  to Git. Use independently constructed synthetic fixtures only.
- Preserve source bytes, source hash and JSON Pointer. Do not silently repair bad
  data, guess units, fill missing measurements with zero or collapse different people.
- Keep CLI output machine-readable. MCP must remain read-only, stdio-only and
  scoped to the configured subject and metric allowlist.
- Exports use Unix milliseconds; official REST examples use nanoseconds. Keep
  adapters separate and verify the actual schema before adding a connector.
- Do not describe a planned or mock connector as working live synchronization.
- Run `python -m unittest discover -s tests -v` and `ruff check .`. Changes to the
  MCP interface also require the optional SDK and the real stdio transport test.
- Maintain upstream references, pinned revisions, license notices and honest
  validation status in the docs. Chinese documentation should use plain wording.
