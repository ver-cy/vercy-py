# Enforcement contract, draft 0.3

Status: draft for review. Not implemented in this package yet. It will first be executed inside the
Graphiti adapter, then shipped as an optional library here.

`vercy check` answers one question: are the Governance Overlay fields present? This contract answers
a different one: does a host that holds those records behave as they say? The two are reported
separately and must never be merged into one badge.

## 1. Who supplies what

| Input | Supplied by | Never taken from |
|---|---|---|
| The records and their overlay fields | The store | - |
| The writer of each record | The host's own write log or authenticated session (`written_by`) | A field inside the record |
| The ownership register: which principal owns which concept | Host configuration | The records |
| The caller: who is asking and which audiences they belong to | The host, from authenticated configuration | The records, the prompt, the query text |
| The scope of the question, as scope values | The caller or the host | The records |
| The as-of date | The caller, or the host clock when none is given | The records |
| The conflict policy | Host configuration, or a record written by the concept's owner | Any other record |

A record can claim anything. `concept_owner` inside a record is a claim about who should own the
concept, checked against the ownership register. A record is **authoritative** for a concept when its
`written_by` is the owner of that concept in the register. Nothing else makes it authoritative.

## 2. Definitions the operations use

- **Validity.** A record is valid at `as_of` when `valid_from <= as_of` and either `valid_to` is null or
  `as_of <= valid_to`. A record with no `valid_from`, or with no `valid_to` key at all, is
  `validity_unknown`: admissible, flagged, and it loses every tie.
- **Scope match.** Exact, case-sensitive equality between one of the question's scope values and one
  value of `applies_to` or `does_not_apply_to`. No substring or semantic matching. A record with
  neither field applies everywhere.
- **Restricted.** A record is restricted when any of `release_to`, `classification`, `confidential`
  or `restricted` has a non-empty value (the same test as the checker: null, empty string, empty list
  and empty object count as absent).
- **Concept.** The host decides which records answer the same concept (same subject and attribute,
  or the same `record_id` lineage). The contract only requires that the decision does not depend on
  who is asking.

## 3. Operations, in this order

1. **Validity.** Drop records not valid at `as_of` (reason `expired`). Keep `validity_unknown`.
2. **Applicability.** Drop records whose `does_not_apply_to` matches, or whose `applies_to` exists and
   does not match (reason `out_of_scope`).
3. **Supersession.** A record named in another record's `supersedes` is dropped (reason `superseded`)
   only if the superseding record is authoritative for the concept and valid. A `supersedes` from a
   non-authoritative writer is ignored and flagged `unauthorized_supersession`. When two records
   supersede each other, neither supersession applies: both stay, and step 4 treats them as a
   conflict.
4. **Precedence.** Among the remaining records for one concept, authoritative records outrank all
   others. Between authoritative records, apply the conflict policy. If it does not decide, the
   result is `abstained`. Non-authoritative records never outrank an authoritative one, whatever
   they assert about priority (reason `unauthorized_precedence` when they try). When no authoritative
   record remains, the same rule applies among the non-authoritative ones: the policy decides, or the
   result is `abstained`, and the answer is flagged `no_authoritative_record`.
5. **Disclosure, last.** Disclosure is applied to the result of steps 1 to 4, not before them. If the
   winning record is restricted and the caller is not in its `release_to`, the outcome is `refused`.
   The host never falls back to a lower-ranked, superseded or older record that the caller may see:
   that would answer with a value the rules already rejected. A restricted record without `release_to`
   is treated as released to nobody (reason `restricted_without_release`).

Running disclosure last is what makes the answer the same for every caller who is allowed to see it,
and makes withholding visible as a refusal instead of a quietly different answer.

## 4. Disclosure boundary

For a record withheld from a caller, nothing derived from it crosses the boundary: not its content,
`record_id`, title, source, owner, dates, citation, snippet, embedding neighbours, summary or any text
generated from it, in the answer, the citations, tool traces or logs returned to the caller. The only
things that may cross are the outcome, a count of withheld records, and the reason codes.

An abstention names only records the caller may see. If any record in the conflict is withheld from
the caller, the outcome is `refused`, not `abstained`, so the existence of the hidden side is not
revealed by name.

## 5. Outcomes and reason codes

| Outcome | Meaning |
|---|---|
| `answered` | One winning record, visible to the caller |
| `abstained` | The top-ranked records disagree, the policy does not decide, all are visible to the caller |
| `refused` | The winning record, or a side of an unresolved conflict, is withheld from this caller |
| `empty` | Nothing relevant survived steps 1 and 2 |

| Reason code | Raised when |
|---|---|
| `expired` | A record was outside its validity interval |
| `validity_unknown` | A record had no `valid_from`, or no `valid_to` key |
| `out_of_scope` | `does_not_apply_to` matched, or `applies_to` did not |
| `superseded` | An authoritative, valid record replaced it |
| `unauthorized_supersession` | A non-authoritative record tried to supersede another |
| `unauthorized_precedence` | A non-authoritative record tried to outrank an authoritative one |
| `conflict_unresolved` | The policy did not decide between the top-ranked records |
| `no_authoritative_record` | No record for the concept was written by its owner |
| `not_released` | The caller is not in `release_to` |
| `restricted_without_release` | A record is restricted but names no audience |

## 6. How a claim of enforcement is tested

A host may say it enforces the overlay only with a passing run of the adversarial fixture, published
with the host version, the access paths covered and the command to rerun it. Expected outcomes are
fixed in the fixture, so the run has an oracle.

| Case | Setup | Pass |
|---|---|---|
| Forged authority | A non-owner writes a record claiming `concept_owner` and a high priority | Owner's record wins; `unauthorized_precedence` raised |
| Forged supersession | A non-owner writes a record that `supersedes` the owner's | Owner's record still answers; `unauthorized_supersession` raised |
| Unauthorized retrieval | A restricted winning record, a caller outside `release_to`, every documented retrieval path (search, graph walk, summary, citation) | `refused`; zero bytes from the withheld record in any payload, per section 4 |
| No fallback | Owner's current record restricted, an older public record superseded by it | `refused`, never the older value |
| Hidden side of a conflict | Two authoritative records disagree, one withheld from the caller | `refused`; the withheld record is not named |
| Unresolved conflict | Two visible authoritative records disagree, policy does not decide | `abstained` naming both |
| Expired truth | A question at a date after `valid_to` | The expired record is not used; `expired` raised |
| Laundered fact | A non-owner restates the owner's fact with a different value, later | The owner's value answers |

The result states which access paths were covered and which were not. A path that was not tested is
reported as not enforced.

## 7. What this contract does not cover

Authentication of callers and writers, storage security, encryption, prompt injection outside the
memory path, and model behaviour after a correct context is assembled. Those belong to the host.
