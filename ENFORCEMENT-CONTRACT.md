# Enforcement contract, draft 0.1

Status: draft for review. Not implemented in this package yet. It will first be executed inside the
Graphiti adapter, then shipped as an optional library here.

`vercy check` answers one question: do the records carry the Governance Overlay fields? This contract
answers a different one: does a host that holds those records behave as they say? The two are
reported separately and must never be merged into one badge.

## 1. Who supplies what

| Input | Supplied by | Never taken from |
|---|---|---|
| The records and their overlay fields | The store | - |
| The caller: who is asking, on whose behalf, which audiences they belong to | The host, from its own authenticated configuration | The records, the prompt, the query text |
| The as-of date of the question | The caller, or the host clock when none is given | The records |
| The conflict policy | The store or the host configuration | A single record that asserts its own priority |

A record can claim anything. Authority comes from configuration the host controls. A record that
names an owner is evidence of who should own it, not proof that its writer is that owner.

## 2. Operations

Given a candidate set of records for one question, an enforcing host applies these in order.

1. **Validity.** Keep records where `valid_from <= as_of` and (`valid_to` is null or `as_of <= valid_to`).
   Records without `valid_from` are not dropped silently: they are kept and flagged `validity_unknown`.
2. **Applicability.** Drop records whose `does_not_apply_to` matches the question's scope. Keep records
   whose `applies_to` matches, or that state no scope.
3. **Disclosure.** For each record with `release_to`, keep it only if the caller belongs to one of the
   named audiences. A restricted record without `release_to` is withheld, not released. Withheld
   content never reaches the model, including in citations, snippets or tool traces.
4. **Precedence.** Where two remaining records answer the same concept differently, apply the conflict
   policy. If the policy does not decide, the answer is an abstention that names both records, never a
   silent pick.
5. **Supersession.** A record named in another record's `supersedes` loses to it, within validity.

## 3. Outcomes and reason codes

Every answer carries one outcome and, where something was removed or refused, stable reason codes.

| Outcome | Meaning |
|---|---|
| `answered` | At least one record survived and no unresolved conflict remains |
| `abstained` | Records disagree and the policy does not decide |
| `refused` | Every relevant record was withheld from this caller |
| `empty` | Nothing relevant was valid at the as-of date |

| Reason code | Raised when |
|---|---|
| `expired` | A record was outside its validity interval |
| `out_of_scope` | `does_not_apply_to` matched, or `applies_to` did not |
| `not_released` | The caller is not in `release_to` |
| `restricted_without_release` | A record is restricted but names no audience |
| `superseded` | A newer record replaces it |
| `conflict_unresolved` | The policy did not decide between records |
| `validity_unknown` | A record had no `valid_from` |

## 4. How a claim of enforcement is tested

A host may say it enforces the overlay only with a passing run of the adversarial fixture, published
with the host version and the command to rerun it. The fixture contains at least:

- **Forged authority.** A record that asserts `concept_owner` and a high-precedence policy for a
  concept it does not own, written by a non-owner. Pass: it does not win precedence.
- **Unauthorized retrieval.** A restricted record queried by a caller outside `release_to`, through
  every retrieval path the host documents (search, graph walk, summary, citation). Pass: zero bytes of
  its content in any returned payload.
- **Unresolved conflict.** Two valid records that disagree, with a policy that does not decide.
  Pass: `abstained` naming both, not a pick.
- **Expired truth.** A question at a date after `valid_to`. Pass: the expired record is not used.
- **Laundered fact.** A fact restated by a lower-authority source after the owner's record. Pass: the
  owner's record still decides.

The result states which access paths were covered and which were not. A path that was not tested is
reported as not enforced.

## 5. What this contract does not cover

Identity and authentication of callers, storage security, encryption, prompt injection outside the
memory path, and model behaviour after a correct context is assembled. Those belong to the host.
