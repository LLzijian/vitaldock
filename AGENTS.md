# VitalDock development instructions

- Product purpose: an agent can fetch the user's latest run on demand, compare
  evidence and inspect recovery context. Huawei native -> Intervals.icu is the
  current primary route. Archive imports are a historical backfill option.
- Never add real health exports, raw vaults, credentials, locations or screenshots
  to Git. Use independently constructed synthetic fixtures only.
- Archive imports preserve source bytes, source hash and JSON Pointer. Live
  responses carry provider, fetch time and a context digest without persistence.
  Do not silently repair bad data, guess units, fill missing measurements with
  zero or collapse different people.
- Keep CLI output machine-readable. MCP remains read-only and stdio-only. Archive
  tools use exact subjects and metric allowlists. Live tools use authenticated
  self (athlete 0), HUAWEI activities, and explicit wellness/streams grants.
- Live tools must re-read the API on each call, report upstream freshness and
  never substitute an older run when a just-completed run has not arrived.
- Compare pace/HR descriptively; do not turn one comparison into a fitness or
  recovery verdict. Do not assume Huawei provides daily HRV or post-stop HR data.
- No Strava API proxy or Strava-sourced activity forwarding. Refer people to
  official Strava MCP where appropriate; verify current provider policies.
- Keep personal API keys in process environment or native OS credential storage.
  No secrets in chat, command arguments, fixture data, logs or committed configs.
- Exports use Unix milliseconds; official REST examples use nanoseconds. Keep
  adapters separate and verify the actual schema before adding a connector.
- Do not describe a planned or mock connector as working live synchronization.
- Health Connect uses its own Android SDK adapter and authenticated USB loopback,
  separate from Huawei/Intervals. Query only startup-granted metric categories,
  preserve origin packages and pagination, and never add overlapping raw sources.
  No GPS, notes, titles or Strava-origin records. Permission dialogs belong to the user.
  Do not claim a fresh phone database read forces a source app or wearable to sync.
- Android changes require testDebugUnitTest, assembleDebug and lintDebug. Keep
  native health read permissions, localhost-only binding and fail-closed pairing.
  Preserve null/empty distinctions and report sampling and partial pages explicitly.
- Run `python -m unittest discover -s tests -v` and `ruff check .`. Changes to the
  MCP interface also require the optional SDK and the real stdio transport test.
- Maintain upstream references, pinned revisions, license notices and honest
  validation status in the docs. Chinese documentation should use plain wording.
- Keep the registration guide, agent API docs and client examples discoverable
  from README. Regenerate interfaces/mcp-tools.json from agent-tools after tool
  changes and verify it matches runtime discovery. Never generate it with keys.
