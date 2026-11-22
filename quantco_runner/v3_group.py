"""Third researcher group (2 Fable + 1 Opus, bottom-up prompts) helpers shared by v3_train.py and the live runner."""
import re, statistics
import session_backtest as sb
INF = float("inf")
RECENCY = ("NEWER RESULTS MATTER MUCH MORE: the market's price level drifts between cases, so weight recent cases far more than old "
           "ones. When price-book rows or past lessons conflict, trust the most recent cases; treat rows from early cases only as a rough prior.")
LOW_SENTENCE = "`low` must be a price you are confident the fair value is AT LEAST: it is exactly what we charge, and charging even 1 EUR above the true fair value loses the whole line, while charging 1 EUR below loses only 1 EUR. `high` is a price you are confident the fair value is below. `fair_gross_total` is your best estimate in between."
V3_LOW_REPLACEMENT = "low/high = your 10th/90th percentile of t, fair_gross_total = your median (see the standing rules)."


def parse_invoice(text):
    """invoice lines with qty/unit from the pdftotext layout (from research/prompt-decompose/extract.py)."""
    items, started, cur = [], False, None
    for ln in text.splitlines():
        if re.search(r"POS\.\s+DESCRIPTION", ln): started = True; continue
        if not started: continue
        if re.search(r"Created on|Page \d", ln) or re.search(r"^\s*(SUBTOTAL|NET|VAT|TOTAL)\b", ln, re.I):
            if cur: items.append(cur); cur = None
            continue
        m = re.match(r"^\s{0,3}(\d{1,2})\s{2,}(.*?)\s{2,}([\d.,]+)\s+([A-Za-z²³][A-Za-z²³0-9./ ]*?)\s*$", ln)
        if m:
            if cur: items.append(cur)
            cur = {"pos": int(m[1]), "desc": m[2].strip(), "qty": float(m[3].replace(",", "")), "unit": m[4].strip()}
        elif cur and ln.strip():
            cur["desc"] += " " + ln.strip()
    if cur: items.append(cur)
    return items


def trade(text):
    m = re.search(r"TRADE\s*\n([^\n]*)", text)
    return re.split(r"\s{2,}", m[1].strip())[-1] if m else ""


def price_book(g, inv, trades, B, max_rows=60):
    """market-proven unit prices from cases < g: all hours lines + lines pinned on both sides (hi/lo < 1.8) + the
    same-trade lines; newest first."""
    rows = []
    for h in range(g - 1, 0, -1):
        for i, it in enumerate(inv.get(h, []), 1):
            lo, hi = sb._sides(B.get(h, {}).get(i))
            lo = lo or 0.0; hi = hi if hi else INF
            if lo <= 0 and hi == INF: continue
            q = it["qty"] or 1.0
            keep = it["unit"].lower().startswith("h") or (lo > 0 and hi < INF and hi / lo < 1.8) or (trades.get(h) and trades.get(h) == trades.get(g))
            if not keep: continue
            rng = (f"fair >= {lo / q:.2f}" if lo > 0 else "never proven fair") + (f", inflated >= {hi / q:.2f}" if hi < INF else "")
            rows.append(f"- case {h} [{trades.get(h, '')}] '{it['desc'][:70]}' ({q:g} {it['unit']}): {rng} per {it['unit'] if it['unit'] != 'flat rate' else 'job'}")
            if len(rows) >= max_rows: break
        if len(rows) >= max_rows: break
    if not rows: return "=== MARKET PRICE BOOK: empty (first case): use general German market knowledge ===\n\n"
    return ("=== MARKET PRICE BOOK (from earlier cases only; GROSS per unit = line total / quantity) ===\n"
            "'fair >= X' = a charge of X was proven fair; 'inflated >= Y' = a charge of Y was proven too high. Newest cases first.\n" + RECENCY + "\n" + "\n".join(rows) + "\n\n")


def feedback(prev, ans, inv, B):
    out = [f"MARKET RESULT for CASE {prev} (judged against your fair_gross_total):"]
    for ln in ans:
        i = ln["index"]; lo, hi = sb._sides(B.get(i)); lo = lo or 0.0; hi = hi if hi else INF; f = ln["fair_gross_total"]
        verdict = ("too low (below the proven-fair charge)" if lo > 0 and f < lo else
                   "too high (at or above a rejected charge)" if f >= hi else "consistent with the market")
        it = inv[i - 1] if inv and len(inv) >= i else None
        unit = ""
        if it and it["qty"] and it["qty"] != 1:
            unit = f" = per {it['unit']}: " + (f"fair >= {lo / it['qty']:.2f}" if lo > 0 else "") + (f", inflated >= {hi / it['qty']:.2f}" if hi < INF else "")
        out.append(f"  line {i}: market {sb.fmt_bound(B.get(i))}{unit}; your fair {f:.2f}: {verdict}")
    return "\n".join(out) + "\nUpdate your per-trade unit rates from this, not a global level. This newest result counts much more than older ones.\n\n"


def optmid(answers, k=0.93, m=0.91):
    valid = [a for a in answers.values() if a]; out = {}
    if not valid: return out
    for i in range(max(len(a) for a in valid)):
        rows = [a[i] for a in valid if len(a) > i]
        cov = sum(bool(r["covered"] and r["related"]) for r in rows) * 2 > len(rows)
        F = statistics.median(r["fair_gross_total"] for r in rows)
        out[i + 1] = (round(k * F, 2), round(m * F, 2)) if cov else (0.0, 0.0)
    return out


