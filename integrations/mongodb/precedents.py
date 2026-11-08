#!/usr/bin/env python3
"""Precedent search: "similar past incidents" for the human reviewer, on MongoDB Atlas Vector Search.

    python integrations/mongodb/precedents.py --run runs/run2 --also submission                 # Atlas (MONGODB_URI)
    python integrations/mongodb/precedents.py --run runs/run2 --backend local                   # no Atlas: local cosine

For each incident in a completed run:
  1. build a short STRUCTURED description (type, supplier/part/plant names, impact size, decision, policy rule).
     No raw event text, no customer ids, no messages: only facts the trace already published.
  2. embed it with Gemini (gemini-embedding-2, 768 dims, SEMANTIC_SIMILARITY); cached per run.
  3. upsert one document per incident into <db>.incidents (_id = run_id:incident_id), ensure a vectorSearch index,
  4. $vectorSearch the top neighbours (same run, other events), and write <run>/similar_incidents.json in the
     contract read by the UI (ui/similar.py).
Scores are on Atlas's cosine scale (1 + cos) / 2 in [0, 1]; the local backend uses the same formula.
"why_similar" is computed in code from shared attributes, never by an LLM. Nothing here changes any decision.
"""
import argparse
import json
import math
import os
import sys
import time
from collections import Counter
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from ripple.extract import GeminiExtractor, load_dotenv  # noqa: E402
from ripple.world import World  # noqa: E402

SCHEMA = "ripple-similar/1.0"
EMBED_MODELS = ["gemini-embedding-2", "gemini-embedding-001"]
DIMS = 768
INDEX = "incident_vec"
CROSS_TYPE_MIN = 0.96   # a precedent of a different incident type is shown only if it is this close
SHORT = {"supplier_delay": "supplier delay", "plant_outage": "plant outage", "quality_hold": "quality hold",
         "noise": "noise", "unconfirmed": "unconfirmed report"}
TYPE_LABEL = {"supplier_delay": "supplier delay", "plant_outage": "plant outage", "quality_hold": "quality hold",
              "noise": "noise (not operational)", "unconfirmed": "unconfirmed report"}


# ---------------------------------------------------------------------------- incident facts
def outcome_of(trace, iid):
    ok = [r for r in trace["execution"] if r["status"] == "confirmed" and iid in (r.get("incidents") or [])]
    c = Counter(r["tool"] for r in ok)
    if c.get("quality.hold_lot") or c.get("dealer.stop_sale") or c.get("crm.notify_customer"):
        return (f"lot held, {c.get('dealer.stop_sale', 0)} dealer stop-sales, "
                f"{c.get('crm.notify_customer', 0)} owners contacted")
    if c.get("mes.reschedule") or c.get("mes.transfer"):
        return (f"{c.get('mes.reschedule', 0)} rescheduled, {c.get('mes.transfer', 0)} transferred, "
                f"{c.get('dealer.notify', 0)} dealers notified, {c.get('crm.assign_loaner', 0)} loaners")
    if any(r["tool"] == "escalate" for r in trace["execution"]):
        return "escalated to a human, no operational change"
    return "no action (no tool calls)"


def incident_docs(traces, world, run_id):
    docs = []
    for t in traces:
        for e in t["incidents"]:
            inc, imp = e["incident"], e.get("impact") or {}
            ent, ev = inc["entities"], imp.get("evidence", {})
            name = lambda table, k: (table.get(ent[k], {}).get("name") if ent.get(k) else None)
            facts = {
                "type": inc["type"], "supplier": ent.get("supplier"), "part": ent.get("part"),
                "plant": ent.get("plant") or (imp.get("disruption") or {}).get("plant"),
                "lot": imp.get("lot"), "models": ev.get("models_needing_part") or ev.get("models_using_part") or [],
                "affected_orders": len(imp.get("affected_pos", [])), "vehicles": ev.get("vehicles_total"),
                "window": ev.get("window"), "decision": e.get("decision"),
                "policy": [p.split(":")[0] for p in imp.get("policy", e.get("policy", []))]}
            parts = [f"incident type: {TYPE_LABEL.get(inc['type'], inc['type'])}"]
            if facts["supplier"]:
                parts.append(f"supplier: {name(world.suppliers, 'supplier')}")
            if facts["part"]:
                p = world.parts.get(facts["part"], {})
                parts.append(f"part: {p.get('name', facts['part'])} ({p.get('category', '')})")
            if facts["plant"]:
                parts.append(f"plant: {world.plants.get(facts['plant'], {}).get('name', facts['plant'])}")
            if facts["models"]:
                parts.append(f"models: {', '.join(facts['models'])}")
            if facts["window"]:
                parts.append(f"window: {facts['window']}")
            if facts["affected_orders"]:
                parts.append(f"{facts['affected_orders']} production orders affected")
            if facts["vehicles"]:
                parts.append(f"{facts['vehicles']} vehicles traced")
            if not imp:
                parts.append(f"why: {inc.get('extractor_reason', '')}")
            parts.append(f"decision: {facts['decision']}")
            parts.append(f"policy: {', '.join(facts['policy'])}")
            docs.append({"_id": f"{run_id}:{inc['incident_id']}", "run_id": run_id, "incident_id": inc["incident_id"],
                         "event_id": t["event_id"], "received_at": t["received_at"], "facts": facts,
                         "description": ". ".join(parts), "decision": facts["decision"], "type": inc["type"],
                         "outcome": outcome_of(t, inc["incident_id"])})
    return docs


def why_similar(a, b):
    fa, fb, w = a["facts"], b["facts"], []
    for k, label in (("part", "part"), ("supplier", "supplier"), ("plant", "plant")):
        if fa.get(k) and fa.get(k) == fb.get(k):
            w.append(f"same {label} {fa[k]}")
    shared = sorted(set(fa.get("models") or []) & set(fb.get("models") or []))
    if shared and not any(x.startswith("same part") for x in w):
        w.append(f"shared models {', '.join(shared)}")
    if not w:
        w.append(f"same incident type ({SHORT.get(fa['type'], fa['type'])})" if fa["type"] == fb["type"]
                 else f"similar description ({SHORT.get(fb['type'], fb['type'])})")
    elif fa["type"] == fb["type"]:
        w.insert(0, SHORT.get(fa["type"], fa["type"]))
    return "; ".join(w)


# ---------------------------------------------------------------------------- embeddings
def embed(docs, cache_path):
    cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
    todo = [d for d in docs if cache.get(d["_id"], {}).get("description") != d["description"]]
    model = cache.get("_model")
    if todo:
        g = GeminiExtractor()
        if not g.key:
            sys.exit("GEMINI_API_KEY is needed for embeddings (.env).")
        last = None
        for m in EMBED_MODELS:
            try:
                r = g._req(f"/models/{m}:batchEmbedContents", {"requests": [
                    {"model": f"models/{m}", "content": {"parts": [{"text": d["description"]}]},
                     "taskType": "SEMANTIC_SIMILARITY", "outputDimensionality": DIMS} for d in todo]})
                model = m
                break
            except Exception as e:  # noqa: BLE001
                last = e
        else:
            sys.exit(f"embedding failed: {last}")
        for d, v in zip(todo, r["embeddings"]):
            cache[d["_id"]] = {"description": d["description"], "embedding": v["values"]}
        cache["_model"] = model
        json.dump(cache, open(cache_path, "w"))
    for d in docs:
        vec = cache[d["_id"]]["embedding"]
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        d["embedding"] = [x / norm for x in vec]
    return model, len(todo)


# ---------------------------------------------------------------------------- backends
def neighbours_local(docs, k):
    out = {}
    for a in docs:
        scored = [((1 + sum(x * y for x, y in zip(a["embedding"], b["embedding"]))) / 2, b)
                  for b in docs if b["event_id"] != a["event_id"]]
        out[a["incident_id"]] = [(s, b) for s, b in sorted(scored, key=lambda p: (-p[0], p[1]["incident_id"]))[:k + 8]]
    return out


def neighbours_atlas(docs, k, run_id):
    from pymongo import MongoClient, ReplaceOne
    from pymongo.operations import SearchIndexModel
    uri = os.environ.get("MONGODB_URI")
    if not uri or uri.startswith("<"):
        sys.exit("Set MONGODB_URI in .env (Atlas connection string), or use --backend local.")
    db = MongoClient(uri, appname="ripple-control", serverSelectionTimeoutMS=20000)[os.environ.get("MONGODB_DB", "ripple")]
    col = db["incidents"]
    col.bulk_write([ReplaceOne({"_id": d["_id"]}, {kk: v for kk, v in d.items()}, upsert=True) for d in docs])
    existing = {i["name"]: i for i in col.list_search_indexes()}
    if INDEX not in existing:
        col.create_search_index(SearchIndexModel(name=INDEX, type="vectorSearch", definition={"fields": [
            {"type": "vector", "path": "embedding", "numDimensions": DIMS, "similarity": "cosine"},
            {"type": "filter", "path": "run_id"}]}))
        print("   created vector index", INDEX, "- waiting until it is queryable")
    t0 = time.time()
    while not next(iter(col.list_search_indexes(INDEX)), {}).get("queryable"):
        if time.time() - t0 > 300:
            sys.exit("vector index not queryable after 5 minutes; rerun later")
        time.sleep(5)
    # an index that has just become queryable may still be catching up on the upserts above
    for _ in range(24):
        probe = list(col.aggregate([{"$vectorSearch": {"index": INDEX, "path": "embedding", "queryVector": docs[0]["embedding"],
                                                        "numCandidates": 100, "limit": len(docs), "filter": {"run_id": run_id}}},
                                    {"$project": {"_id": 1}}]))
        if len(probe) >= len(docs):
            break
        time.sleep(5)
    by_id = {d["incident_id"]: d for d in docs}
    out = {}
    for a in docs:
        res = col.aggregate([
            {"$vectorSearch": {"index": INDEX, "path": "embedding", "queryVector": a["embedding"],
                               "numCandidates": 100, "limit": k + 9, "filter": {"run_id": run_id}}},
            {"$project": {"incident_id": 1, "event_id": 1, "score": {"$meta": "vectorSearchScore"}}},
            {"$match": {"event_id": {"$ne": a["event_id"]}}},
            {"$limit": k + 8}])
        out[a["incident_id"]] = [(r["score"], by_id[r["incident_id"]]) for r in res if r["incident_id"] in by_id]
    return out, f"{db.name}.incidents"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="runs/run2")
    ap.add_argument("--also", nargs="*", default=[], help="extra folders to copy similar_incidents.json into (e.g. submission)")
    ap.add_argument("--backend", default="atlas", choices=["atlas", "local"])
    ap.add_argument("--top-k", type=int, default=3)
    a = ap.parse_args()
    load_dotenv()
    w = World.load("data")
    traces = [json.loads(l) for l in open(os.path.join(a.run, "event_traces.jsonl"), encoding="utf-8")]
    run_id = traces[0]["run_id"]
    docs = incident_docs(traces, w, run_id)
    model, fresh = embed(docs, os.path.join(a.run, "incident_embeddings.json"))
    print(f"{len(docs)} incidents from {a.run}; embeddings: {model} ({fresh} new, rest cached)")
    if a.backend == "local":
        nb, store = neighbours_local(docs, a.top_k), None
        source = "local-cosine (same Gemini embeddings; no MongoDB)"
    else:
        nb, store = neighbours_atlas(docs, a.top_k, run_id)
        source = "mongodb-atlas-vector-search"
    by_incident = {}
    for d in docs:   # same-type precedents first; other types only when very close
        nb[d["incident_id"]] = [(s, b) for s, b in nb[d["incident_id"]]
                                if b["type"] == d["type"] or s >= CROSS_TYPE_MIN][:a.top_k]
        by_incident[d["incident_id"]] = [
            {"incident_id": b["incident_id"], "event_id": b["event_id"], "type": b["type"], "score": round(s, 4),
             "decision": b["decision"], "outcome": b["outcome"], "why_similar": why_similar(d, b)} for s, b in nb[d["incident_id"]]]
    out = {"schema_version": SCHEMA, "source": source, "run_id": run_id,
           "generated_at": datetime.now().replace(microsecond=0).isoformat(), "top_k": a.top_k,
           "embedding_model": model, "store": store, "by_incident": by_incident}
    for folder in [a.run] + a.also:
        json.dump(out, open(os.path.join(folder, "similar_incidents.json"), "w", encoding="utf-8"), indent=2)
        print("   wrote", os.path.join(folder, "similar_incidents.json"))
    for iid in ("E-12#1", "E-03#1", "E-02#1"):
        print(f"   {iid}: " + "; ".join(f"{n['incident_id']} {n['score']:.3f} ({n['why_similar']})" for n in by_incident.get(iid, [])))


if __name__ == "__main__":
    main()
