# Architecture

One turn, from what the pupil says to what they get back:

```
what the pupil said (typed, or a recording transcribed first)
        │
        ▼
  topical guard ─────────────► off topic  → a kind reply, counted, escalated at the threshold
  (school use? off topic?      welfare    → a caring reply, never counted, never stored
   distress?)                  uncertain  → answered, but no tools
        │ on topic (a ValidatedTurn is issued)
        ▼
  retrieval: the query is embedded locally, then L1 cache → L2 the DLL chain → L3 LanceDB,
  with BMJ routing promoting at most one block per search
        │
        ▼
  the tutor model answers, and may call tools on this turn only:
     web_search      → the query is classified on its own before anything is sent
     save_to_notebook→ writes to the pupil's notebook, which this turn can never read back
                       (a revision sheet the pupil asks for is the one path out, and it
                        goes to the write-back model, bounded, never to this one)
        │
        ▼
  the answer is rendered for the channel (text, spoken, braille) with its sources
        │
        ▼
  memory write-back: a small model turns the exchange into JSON, stored in L2 and paged to L3
```

Where each piece lives:

| Layer | What it is | Code |
|---|---|---|
| L1 | in-process cache, per-type TTL | `apu/mmu/cache_l1.py` |
| L2 | the DLL: a doubly linked list of memory blocks, persisted as JSON, LRU page-out | `apu/mmu/dll.py` |
| L3 | LanceDB: downloaded courses and archived pupil memory | `apu/storage/lance_driver.py` |
| Guard | NeMo Guardrails rail, per-class policy, escalations | `apu/guardrails/` |
| Tools | web search and the notebook, both gated on the turn's proof | `apu/tools/` |
| Modality | interaction modes, citations, braille, speech | `apu/modality/` |
| Interfaces | the pupil's chat, and the teacher, admin and demo pages | `apu/ui/` |

Two things kept out of the tutoring memory on purpose: escalation events
(`apu/mmu/escalation_store.py`) and the pupil's notebook (`apu/notebook/`). Neither is a DLL
block, neither is searched, and the DLL and the L3 driver refuse the escalation block type
outright.

This implementation is Akili, the education line of the Agent Processor Unit
(`github.com/EZFRICA/Agent-Processor-Unit`). It differs from the reference APU: no Redis, no
Weaviate, no L4 archive, and the routing decisions that diverge are listed in
[decisions.md](./decisions.md). The longer design rationale (why a doubly linked list rather
than a graph, how BMJ routing behaves on constrained hardware) is in the Medium series "From
Agent OS to Agent Processor Unit" and "Implementing the Agent Processor Unit: A Tutor That
Runs Offline".
