#!/usr/bin/env python
"""Evaluation harness. Never invents ground truth.

  python scripts/evaluate_models.py export-templates [--n 200]   # write annotation sheets into docs/annotation/
  python scripts/evaluate_models.py run                          # compute every metric that has data behind it

What `run` reports
  1. PROXY sentiment check (always available): VADER vs a rating-derived weak label (>=4 pos, <=2 neg, 3 neu).
     This is NOT ground truth – star ratings and review text legitimately disagree. Shown only as a sanity signal
     and to compare the baseline against the domain-extended lexicon.
  2. Sentiment accuracy/precision/recall/F1/confusion matrix against YOUR manual labels (docs/annotation/sentiment_annotations.csv).
  3. Aspect extraction precision/recall and aspect-sentiment accuracy against YOUR manual labels (aspect_annotations.csv).
  4. Ranking vs a rating-only baseline against YOUR relevance judgments (ranking_judgments.csv) + coverage/uncertainty.
  5. Restaurant-matching precision from YOUR verification of a sample (match_verification.csv) + unmatched statistics.
Anything without annotations is reported as "not evaluated" with the reason.
"""
import argparse
import json
import math
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from _common import session
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support
from sqlalchemy import select

from backend.config import ROOT
from backend.models import BertSentimentResult, Restaurant, RestaurantRanking, Review
from backend.nlp.aspects import ASPECTS, analyze_review_aspects
from backend.nlp.sentiment import score_text
from backend.services.ranking import VALID_REVIEW_STATUSES

ANN = ROOT / "docs" / "annotation"
OUT = ROOT / "docs" / "evaluation_results.json"
LABELS = ["positive", "neutral", "negative"]


def _valid_reviews(db):
    return list(db.scalars(select(Review).where(Review.restaurant_id.is_not(None), Review.match_status.in_(VALID_REVIEW_STATUSES))))


# ----------------------------------------------------------------------------- templates
def export_templates(n: int, seed: int = 42):
    ANN.mkdir(parents=True, exist_ok=True)
    db = session()
    revs = _valid_reviews(db)
    rnd = random.Random(seed)
    sample = rnd.sample(revs, min(n, len(revs)))
    # model outputs are deliberately NOT included, so annotators are not anchored by them
    pd.DataFrame([{"review_id": r.id, "text": r.text, "human_sentiment": ""} for r in sample]).to_csv(ANN / "sentiment_annotations.csv", index=False)
    pd.DataFrame([{"review_id": r.id, "text": r.text, **{f"{a}": "" for a in ASPECTS}} for r in sample[: max(1, n // 2)]]).to_csv(ANN / "aspect_annotations.csv", index=False)
    matched = list(db.scalars(select(Review).where(Review.match_status == "matched")))
    by_rest = {}
    for r in matched:
        by_rest.setdefault(r.restaurant_id, r)
    ids = rnd.sample(list(by_rest), min(50, len(by_rest)))
    rows = []
    for rid in ids:
        rest, rv = db.get(Restaurant, rid), by_rest[rid]
        rows.append({"restaurant_id": rid, "osm_name": rest.name, "osm_address": rest.address, "osm_url": rest.source_url,
                     "zomato_name": rv.source_restaurant_name, "zomato_address": (rv.match_evidence or {}).get("source_address"), "is_correct_match": ""})
    pd.DataFrame(rows).to_csv(ANN / "match_verification.csv", index=False)
    rated = list(db.scalars(select(Restaurant).join(RestaurantRanking).where(RestaurantRanking.popularity_score.is_not(None))))
    pd.DataFrame([{"restaurant_id": r.id, "name": r.name, "neighborhood": r.neighborhood, "judge_1_to_5_how_recommendable": ""} for r in rnd.sample(rated, min(60, len(rated)))]).to_csv(ANN / "ranking_judgments.csv", index=False)
    print(f"Wrote annotation templates to {ANN}\n"
          "Sentiment: fill human_sentiment with positive/neutral/negative.\n"
          "Aspects: for each aspect column enter positive/neutral/negative, or leave BLANK if the review does not mention it.\n"
          "Matches: is_correct_match = yes/no (check the OSM URL against the Zomato name/address).\n"
          "Ranking: rate how recommendable each restaurant is (1-5) from your own knowledge or by looking at it.")


# ----------------------------------------------------------------------------- metrics
def _prf(y_true, y_pred, labels=LABELS):
    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "per_class": {l: {"precision": round(float(p[i]), 4), "recall": round(float(r[i]), 4), "f1": round(float(f[i]), 4), "support": int(s[i])} for i, l in enumerate(labels)},
        "macro_f1": round(float(f.mean()), 4),
        "confusion_matrix": {"labels": labels, "rows_true_cols_pred": confusion_matrix(y_true, y_pred, labels=labels).tolist()},
        "n": len(y_true),
    }


def _read(name):
    p = ANN / name
    return pd.read_csv(p, dtype=str, keep_default_na=False) if p.exists() else None


def _bert_labels(db, ids):
    """Stored BERT labels (never recomputed here). Reviews BERT has not scored are simply absent."""
    ids = list(ids)
    out = {}
    for i in range(0, len(ids), 500):
        for rid, lab in db.execute(select(BertSentimentResult.review_id, BertSentimentResult.label).where(BertSentimentResult.review_id.in_(ids[i:i + 500]))):
            out[rid] = lab
    return out


def _bert_block(db, ids, y, vader_pred, bert_by_id, extra):
    """BERT vs VADER on the SAME reviews (the subset BERT has scored), so the two are comparable."""
    keep = [k for k, rid in enumerate(ids) if rid in bert_by_id]
    if not keep:
        return {"status": "not evaluated", "reason": "no stored BERT predictions (run python scripts/run_bert.py first)"}
    yy = [y[k] for k in keep]
    return {"status": "evaluated", "n": len(keep), "bert": _prf(yy, [bert_by_id[ids[k]] for k in keep]),
            "vader_baseline_same_reviews": _prf(yy, [vader_pred[k] for k in keep]), **extra}


def proxy_sentiment(revs, db=None):
    pairs = [(r.text, "positive" if r.rating >= 4 else "negative" if r.rating <= 2 else "neutral") for r in revs if r.rating is not None]
    pair_ids = [r.id for r in revs if r.rating is not None]
    if not pairs:
        return {"status": "not evaluated", "reason": "no reviews with star ratings"}
    y = [l for _, l in pairs]
    out = {"status": "proxy only – NOT ground truth", "n": len(pairs), "label_distribution": dict(Counter(y)),
           "definition": "weak label from the reviewer's own star rating: >=4 positive, 3 neutral, <=2 negative"}
    for name, ext in (("vader_baseline", False), ("vader_plus_domain_lexicon", True)):
        out[name] = _prf(y, [score_text(t, extended=ext).label for t, _ in pairs])
    if db is not None:
        out["bert_vs_vader"] = _bert_block(db, pair_ids, y, [score_text(t, extended=False).label for t, _ in pairs], _bert_labels(db, pair_ids),
                                           {"caveat": "Proxy labels again: agreement with the reviewer's own stars, not accuracy against ground truth."})
    return out


def manual_sentiment(db):
    df = _read("sentiment_annotations.csv")
    if df is None:
        return {"status": "not evaluated", "reason": "run export-templates and annotate"}
    df = df[df.human_sentiment.str.strip().str.lower().isin(LABELS)]
    if len(df) < 30:
        return {"status": "not evaluated", "reason": f"only {len(df)} annotated rows (need >= 30 for stable metrics)"}
    texts = {r.id: r.text for r in db.scalars(select(Review).where(Review.id.in_([int(i) for i in df.review_id])))}
    y = [h.strip().lower() for h in df.human_sentiment]
    out = {"status": "evaluated against manual labels", "n": len(df)}
    for name, ext in (("vader_baseline", False), ("vader_plus_domain_lexicon", True)):
        out[name] = _prf(y, [score_text(texts[int(i)], extended=ext).label for i in df.review_id])
    rid = [int(i) for i in df.review_id]
    out["bert_vs_vader"] = _bert_block(db, rid, y, [score_text(texts[i], extended=False).label for i in rid], _bert_labels(db, rid),
                                       {"caveat": "Computed on the labelled reviews that BERT has scored; small samples give wide uncertainty."})
    return out


def manual_aspects(db):
    df = _read("aspect_annotations.csv")
    if df is None:
        return {"status": "not evaluated", "reason": "run export-templates and annotate"}
    filled = df[df[ASPECTS].apply(lambda r: any(v.strip() for v in r), axis=1)] if len(df) else df
    if len(filled) < 20:
        return {"status": "not evaluated", "reason": f"only {len(filled)} rows contain any aspect annotation (need >= 20; blank = not mentioned, so annotate every row you reviewed)"}
    # Rows are only trusted as fully annotated when the annotator touched them; unmentioned aspects stay blank.
    texts = {r.id: r.text for r in db.scalars(select(Review).where(Review.id.in_([int(i) for i in df.review_id])))}
    tp = fp = fn = 0
    sent_ok = sent_n = 0
    per = {a: {"tp": 0, "fp": 0, "fn": 0} for a in ASPECTS}
    for _, row in df.iterrows():
        pred = {m.aspect: m.label for m in analyze_review_aspects(texts[int(row.review_id)])}
        for a in ASPECTS:
            gold = row[a].strip().lower()
            gold = gold if gold in LABELS else None
            if gold and a in pred:
                tp += 1; per[a]["tp"] += 1
                sent_n += 1; sent_ok += int(pred[a] == gold)
            elif a in pred:
                fp += 1; per[a]["fp"] += 1
            elif gold:
                fn += 1; per[a]["fn"] += 1
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    return {"status": "evaluated against manual labels", "n_reviews": len(df),
            "extraction": {"precision": prec and round(prec, 4), "recall": rec and round(rec, 4), "tp": tp, "fp": fp, "fn": fn,
                           "per_aspect": {a: {**c, "precision": round(c["tp"] / (c["tp"] + c["fp"]), 4) if c["tp"] + c["fp"] else None,
                                              "recall": round(c["tp"] / (c["tp"] + c["fn"]), 4) if c["tp"] + c["fn"] else None} for a, c in per.items()}},
            "aspect_sentiment_accuracy": {"accuracy": round(sent_ok / sent_n, 4) if sent_n else None, "n": sent_n,
                                          "note": "only over aspects both annotator and system found"}}


def _spearman(a, b):
    ra, rb = pd.Series(a).rank(), pd.Series(b).rank()
    return float(ra.corr(rb)) if len(a) > 2 else None


def _ndcg_at_k(rel_by_rank, k=10):
    dcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rel_by_rank[:k]))
    ideal = sorted(rel_by_rank, reverse=True)
    idcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(ideal[:k]))
    return dcg / idcg if idcg else None


def manual_ranking(db):
    df = _read("ranking_judgments.csv")
    if df is None:
        return {"status": "not evaluated", "reason": "run export-templates and annotate"}
    df = df[df.judge_1_to_5_how_recommendable.str.strip().isin(list("12345"))]
    if len(df) < 15:
        return {"status": "not evaluated", "reason": f"only {len(df)} judged restaurants (need >= 15)"}
    rows = []
    for _, r in df.iterrows():
        rest = db.get(Restaurant, int(r.restaurant_id))
        if rest and rest.ranking and rest.ranking.popularity_score is not None:
            rows.append((int(r.judge_1_to_5_how_recommendable), rest.ranking.popularity_score, rest.rating if rest.rating is not None else float("nan")))
    rows = [x for x in rows if not math.isnan(x[2])]
    if len(rows) < 15:
        return {"status": "not evaluated", "reason": "too few judged restaurants with both a rating and a score"}
    rel, score, rating = zip(*rows)
    by_score = [r for _, r in sorted(zip(score, rel), key=lambda t: -t[0])]
    by_rating = [r for _, r in sorted(zip(rating, rel), key=lambda t: -t[0])]
    return {"status": "evaluated against manual relevance judgments", "n": len(rows),
            "spearman_vs_judgment": {"foodspotter_score": _spearman(score, rel), "rating_only_baseline": _spearman(rating, rel)},
            "ndcg_at_10": {"foodspotter_score": _ndcg_at_k(by_score), "rating_only_baseline": _ndcg_at_k(by_rating)},
            "uncertainty_note": f"n={len(rows)} is small; differences between the two rankings are not statistically tested – treat as indicative.",
            "judges": "single annotator unless you add more"}


def manual_matching(db):
    df = _read("match_verification.csv")
    total_matched = db.scalar(select(__import__("sqlalchemy").func.count(Review.id)).where(Review.match_status == "matched")) or 0
    unresolved = dict(db.execute(select(Review.match_status, __import__("sqlalchemy").func.count()).group_by(Review.match_status)).all())
    base = {"review_counts_by_match_status": unresolved, "matched_reviews": total_matched,
            "note": "needs_review / ambiguous reviews are excluded from all analytics and rankings"}
    if df is None:
        return {"status": "not evaluated", "reason": "run export-templates and verify the sample", **base}
    d = df[df.is_correct_match.str.strip().str.lower().isin(["yes", "no"])]
    if len(d) < 20:
        return {"status": "not evaluated", "reason": f"only {len(d)} verified (need >= 20)", **base}
    wrong = int((d.is_correct_match.str.lower() == "no").sum())
    n = len(d)
    p = (n - wrong) / n
    z = 1.96
    lo = (p + z * z / (2 * n) - z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / (1 + z * z / n)
    return {"status": "evaluated against manual verification", "verified_sample": n, "incorrect_matches": wrong,
            "precision": round(p, 4), "precision_95ci_lower_wilson": round(lo, 4), **base}


def run():
    db = session()
    revs = _valid_reviews(db)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {"verified_reviews": len(revs), "restaurants": db.scalar(select(__import__("sqlalchemy").func.count(Restaurant.id))),
                    "note": "Historical dataset snapshot; results do not describe current restaurant quality."},
        "sentiment_proxy": proxy_sentiment(revs, db),
        "sentiment_manual": manual_sentiment(db),
        "aspects_manual": manual_aspects(db),
        "ranking_vs_rating_baseline": manual_ranking(db),
        "restaurant_matching": manual_matching(db),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, default=str))
    for k, v in result.items():
        if isinstance(v, dict) and "status" in v:
            print(f"{k:30s} {v['status']}" + (f" – {v['reason']}" if "reason" in v else ""))
    print(f"\nFull results: {OUT}")
    db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export-templates")
    e.add_argument("--n", type=int, default=200)
    sub.add_parser("run")
    a = ap.parse_args()
    export_templates(a.n) if a.cmd == "export-templates" else run()
