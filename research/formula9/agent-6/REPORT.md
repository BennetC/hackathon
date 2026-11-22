# Formula agent 6: "cap G3 by the group consensus, shave 8 %, accept up to the estimate"

Read-only analysis. No submits, no model calls, no state.json writes. Scripts are in this folder. The fast per-line replay
(`data.py`) matches `fable_vs_opus.replay` exactly (checked on games 3, 17, 30, 41 and 47).

## The rule (per invoice line)

```
gate   : covered = (# of the 9 researchers with covered & related) > half of the researchers present
G_i    : median fair_gross_total of group i (G1 = 3 old Opus, G2 = Fable + 2 Opus, G3 = new bottom-up group),
         using only groups whose own majority says covered
X      : min( G3 , median(G1, G2, G3) )            (if G3's majority says uncovered: X = median of the covering groups)
a      : 0.92 · X        if covered, else 0
b      : 1.00 · X        if covered, else 0
```

Why each term is there:
- **Gate:** we only charge or accept lines that most researchers call covered. This follows Daniil's constraint. Lines a minority calls covered are in an extra column only.
- **G3 as the anchor:** G3 prices bottom-up against a market price book, so it is the best-calibrated group. On mature games its median sits at about 0.97 × the market's proven-fair level.
- **Capped by the median of the groups:** overpricing loses the whole line, underpricing costs only the difference. So when two other independent groups both price below G3, we take the lower consensus.
- **k = 0.92:** a small safety margin for leftover noise. Every base tested has a cliff at k ≈ 0.95–0.96 (worst case −50 K for +0.03).
- **m = 1.00:** we accept anything up to our own cautious fair estimate. The odd-game cost curve is flat for m = 0.96–1.02, so no multiplier is needed.

The rule has two parameters and does not use the judges. On odd games, no combination with judges helped:
- **As a cap on the charge:** 1–26 K worse.
- **As the base for the limit b:** 4–12 K worse than X.

## Results (net, worst..best, midpoint). k and m were tuned on odd games only. Even games were never used for fitting.

| rule | odd 1-47 (fit) | even 2-46 (validation) | even 36-46 |
|---|---|---|---|
| **FINAL k=0.92, m=1.00** | **+63.6K..+150.0K (mid +106.8K)** | **+57.9K..+124.5K (mid +91.2K)** | **+29.1K..+51.7K (mid +40.4K)** |
| Baseline Ruben, 2 groups (live) | +48.7K..+176.8K (mid +112.7K) | +47.2K..+198.0K (mid +122.6K) | +24.7K..+62.1K (mid +43.4K) |
| Baseline Ruben, 3 groups | +46.8K..+201.0K (mid +123.9K) | +57.0K..+197.0K (mid +127.0K) | +26.8K..+63.9K (mid +45.3K) |
| (ref) G3 alone 0.93/0.91 | +55.4K..+193.3K (mid +124.3K) | +51.4K..+181.9K (mid +116.7K) | +32.0K..+71.2K (mid +51.6K) |
| extra col: charge if any group's majority says covered | +65.8K..+152.4K | +57.9K..+124.5K | +29.1K..+51.7K |

The baselines reproduce the brief's numbers for games 36-47: 2 groups +35.6K..+84.8K, 3 groups +38.2K..+89.8K, G3 alone +44.0K..+95.7K. FINAL scores +45.1K..+77.3K on 36-47.

Where the difference comes from, split by side (worst..best totals; `decomp_out.txt`):
- **Limit b:** it pays less in both worst and best case. Paid worst case is 197.6 vs 211.2 K on odd games and 174.0 vs 176.3 K on even games, against the live baseline.
- **Charge a:** worst case is about the same as Ruben (261 vs 260 K odd, 232 vs 223 K even). Best case is much lower (329 vs 370 K odd), because a lower charge leaves fewer "?" lines that would pay 1.5a if they were fair.

**Caveat:** FINAL wins on the worst case (the primary score), but loses on best case and midpoint against both baselines (even midpoint +91K vs +123/+127K). If you believe the midpoint, keep the baselines' higher charges.

## Robustness (worst case, K: odd / even / even 36-46)

- **k ±0.02:**
  - k = 0.90: +56.9 / +57.2 / +31.9
  - k = 0.94: +69.0 / **+33.4 / +11.7** (even games fall off the cliff)
- **k ±0.05:**
  - k = 0.87: +47.8 / +46.6 / +25.4
  - k = 0.97: **−47.6 / −17.9 / −36.7**
- **m:** flat. Between 0.98 and 1.02 it moves less than ±1.5K. At 0.95 or 1.05 it costs 2–7K.
- **Bootstrap of the k choice on odd games** (500 resamples, choosing k by the mean of k−0.02, k, k+0.02):
  - k: 0.92 in 69 %, 0.93 in 22 %.
  - m: 0.99 in 54 %, 1.00 in 24 %.
  - The raw odd-game optimum is 0.94, right at the cliff. That is why I use the guarded 0.92.
- **Bootstrap over games, FINAL minus baseline in worst case** (median [90 % CI], P > 0):

  | | vs Ruben 2 groups | vs Ruben 3 groups |
  |---|---|---|
  | odd games | +14.9K [−17.9, +58.7], P = 0.74 | +16.0K [−3.7, +45.5], P = 0.90 |
  | even games | +10.2K [−10.9, +34.6], P = 0.76 | +0.9K [−10.7, +11.5], P = 0.55 |

- **The edge is concentrated:** game 33 alone gives +19.3K on odd games. G1 is missing in game 33. G3 = 1250 was below the market lo of 1220/0.92, while the baseline's average of groups charged above it. That is exactly the case the cap is meant for.

## How I chose (with full disclosure)

All candidates used X × (k, m), with k and m fitted on odd games under the cliff guard. Odd-game worst case:

| base X | odd worst case |
|---|---|
| min of groups | +80.8K |
| min(G3, median of groups) | +63.9K |
| G3 only | +54.6K |
| median of 9 covered fairs | +43.2K |
| median of groups | +40.6K |

I first took **min of groups**. Its odd-game lead comes from one line: game 29 line 1, where the market lo is 1532, G1 = 1500 and G3 = 2000, worth about 21K. Odd-only checks then favoured min(G3, median):
- **Odd worst case without game 29:** +74.9K vs +70.7K.
- **Odd midpoint:** +107.0K vs +105.6K.
- **Odd best case:** +150K vs +130K.
- **Odd games 36-47, where G3 is mature:** +16.2K vs +10.3K.

I did see min-of-groups' even result (+52.7K, even 36-46 +16.9K) before switching. The reasons I give for the switch are odd-only, but the decision was not blind.

## Recommendation

FINAL is a modest worst-case improvement and should not be switched to blindly. It beats both baselines in worst case on odd games (+15–17K) and on even games 36-46 (+2–4K). On all even games it beats the live 2-group rule (+10.7K) and ties the 3-group rule (+0.9K). It is clearly worse on best case and midpoint.

What is safe to adopt now:
1. **b = 1.00 × X.** It improves both bounds of the paid side on both splits, against both baselines.
2. **The "never charge above G3 when G3 is lower than the consensus" cap.** This idea drives most of the charge-side wins, but I did not test it on top of the baseline's charge by itself.

Whether to also lower the charge (k = 0.92 on X instead of the baseline's mean of group charges) depends on whether we optimise worst case (yes) or midpoint (no).
