# Design decisions

Architecture decision records for the rebuild described in [the launch plan](../launch-plan/ROADMAP.md).
Each ADR states the decision, the evidence behind it and the work it implies. Spikes that back an ADR live
under [`spikes/`](../../spikes/).

| ADR | Title | Status |
|---|---|---|
| [0001](0001-vault-engine.md) | One vault engine that owns the key, the index and consent (engine process, IPC, SQLCipher store, key hierarchy, consent/audit, MCP shim, Tauri sidecar, migration, Phase 1 PR plan) | Proposed |
