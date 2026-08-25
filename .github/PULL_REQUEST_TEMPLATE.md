<!-- ledger-contract: pull-request/v1 -->
<!--
This is a static ledger form. Use concrete durable URLs and current-head evidence.
Offline validation checks shape and internal consistency only; it does not prove
GitHub object existence, authorship, edit history, chronology, labels, or live ritual state.
Do not grant authority to a GitHub Projects board, fabricate historical ritual records,
or claim that K10 or K11 is implemented.
-->

## Task relationship

<!-- field:task_relationship type:input required:true -->
### Task relationship

<!--
Description: Enter exactly Closes or Refs followed by one canonical same-repository Task Issue URL; a bare URL is invalid.
Prompt: Closes or Refs followed by one canonical same-repository Task Issue URL; no default.
-->

<!-- field:plan_comment_url type:input required:true -->
### Plan comment URL

<!--
Description: A concrete same-Task issuecomment URL; offline validation does not prove existence, authorship, edit history, or chronology.
Prompt: Enter one concrete issuecomment URL belonging to the primary Task.
-->

## Summary and scope

<!-- field:summary type:textarea required:true -->
### Summary

<!--
Description: Summarize the durable outcome.
Prompt: Describe what changed and why.
-->

<!-- field:scope type:textarea required:true -->
### Scope

<!--
Description: List changed surfaces and explicit exclusions.
Prompt: One included or excluded surface per line.
-->

## Evidence table

<!-- field:head_sha type:input required:true -->
### Exact head SHA

<!--
Description: Bind evidence to the exact 40-character lowercase pull-request head SHA.
Prompt: Enter the exact 40-character lowercase pull-request head SHA.
-->

<!-- field:evidence type:textarea required:true -->
### Evidence

<!--
Description: For every row provide ID, Task criterion ID, check, result, evidence URL, head SHA, and observed-at timestamp. Commit/check URLs are SHA-bound; Actions URL-to-head association is not proven offline.
Prompt: | ID | Criterion ID | Check | Result | Evidence URL | Head SHA | Observed at |
|---|---|---|---|---|---|---|
-->

## Risks and limitations

<!-- field:risks type:textarea required:true -->
### Risks

<!--
Description: List remaining risks. Use None only when no risk remains.
Prompt: One risk per line, or None.
-->

<!-- field:limitations type:textarea required:true -->
### Limitations

<!--
Description: State unimplemented or unverified boundaries without overclaiming.
Prompt: One limitation per line, or None.
-->

## Deferred evidence

<!-- field:deferred_evidence type:textarea required:true -->
### Deferred evidence

<!--
Description: Use None, or provide ID, Task criterion ID, reason, owner, and same-repository follow-up Issue URL for every deferred item.
Prompt: None, or use: | ID | Criterion ID | Reason | Owner | Follow-up Issue URL |
|---|---|---|---|---|
-->
