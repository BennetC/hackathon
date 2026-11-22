# 04 Strategy math

What each decision costs or earns, per line and per opponent. How `a` and `b` are chosen
is up to each strategy; this document only defines the quantities a strategy works with.

## Notation

- `t`: hidden fair value of the line (gross EUR line total); `t = 0` if not covered or unrelated.
- `c`: hidden payment cap, `c ≥ 4·t` with an absolute floor.
- `G`: our belief distribution of `t`, with survival `S(x) = P(t ≥ x)`. Coverage
  uncertainty is a point mass: `t = 0` with probability `p_excl`, otherwise `t ~ price model`.
- `F(x) = P(opponent b < x)`: share of opponents who reject a charge of `x`.

## What gets accepted, rejected and paid

A charge `a` from issuer H to reviewer I is **accepted** if `a ≤ b_I`, otherwise **rejected**.
It is **fair** if `a ≤ t`, otherwise **inflated**. I pays H:

| | fair (`a ≤ t`) | inflated (`a > t`) |
|---|---|---|
| accepted (`a ≤ b`) | `a` | `min(a, c)` |
| rejected (`a > b`) | `1.5·a` | `0` |

Boundaries: `a = t` is fair, `a = b` is accepted. An omitted line counts as `a = 0, b = 0`.

## Insurer side: cost of an incoming charge `a`

Depends only on the incoming `a`, our `b` and `t`, never on other insurers.

```
cost(accept | a) = S(a)·a + (1 − S(a))·min(a, c)
cost(reject | a) = 1.5·a·S(a)
```

Relative to the outcome-optimal decision, a wrong decision costs:

| Bill is… | Accept costs | Reject costs | Cost of the wrong choice |
|---|---|---|---|
| fair | `a` | `1.5·a` | wrongful rejection: `+0.5·a` |
| inflated | `min(a, c)` | `0` | wrongful acceptance: `+min(a, c)` |

`b` is a single threshold per line, so it applies to every incoming charge on that line.

## Handyman side: income from our charge `a`

Depends on the opponents' `b`, summarised by `F`:

```
E[income | a] = S(a) · a · (1 + 0.5·F(a))            # fair: paid a, or 1.5a if rejected
              + (1 − S(a)) · min(a, c) · (1 − F(a))   # inflated: paid only if accepted
```

Limiting cases:
- `F ≈ 1` (opponents reject everything above `t`): the second term vanishes.
- `F ≈ 0` (opponents accept everything): `E = min(a, c)`, regardless of `t`.

`F` can be estimated from our own settled transactions (which of our charges were accepted
or rejected, and whether a rejection paid `1.5·a` or `0`).

## What `t` is

`t` ≈ the expert-accepted gross line total: quantity × reasonable unit price × (1 + VAT),
in EUR, and `0` if the line is not covered by the policy or not related to the damage.

## Feedback

Settled games show, for our own team, which charges were accepted or rejected and what was
paid. Use only what the official leaderboard shows. Do **not** probe for thresholds.
