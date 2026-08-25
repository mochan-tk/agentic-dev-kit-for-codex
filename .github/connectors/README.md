# Connector-neutral context interface

The portable core consumes one reviewed context contract and never requires a
particular connector. T08 defines the interface only; it does not ship or
activate an external-service, builtin, or vendor connector.
Connector metadata schemas and concrete connector-definition validation are
deferred until a concrete connector is reviewed.

The machine-readable contract is `connector-contract.v1.json`. The interface
has exactly four operations; an eventual connector implements all four:

| Operation | Contract |
|---|---|
| `discover` | Read-only detection and bounded source enumeration. |
| `retrieve` | Read-only source observation with bounded in-memory provenance output. |
| `pin` | Produce a proposed exact `context-pin/v1` record for review. |
| `verify` | Verify historical validity and selected-pin freshness without silently re-pinning. |

Every operation reports one of `pass`, `fail`, `drift`, `UNKNOWN`, or
`UNCHECKABLE`; only `pass` is success. Sensors remain read-only. A later pin
write is an explicit actuator and does not become accepted merely because an
agent produced it.

No account, network service, credential, MCP server, SDK, Skill, custom agent,
hook, or runtime adapter is mandatory. Connector-specific configuration must
stay outside the core operation records. Durable outputs use closed schemas
and exclude credential values, private keys, environment dumps, raw
transcripts, raw logs, and private absolute local paths.

If retrieved material is later written into the repository, that write is a
separate explicit proposal actuator with reviewed ownership. `retrieve` itself
never silently lands or reconciles files.
