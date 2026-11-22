# 01 Game rules (formal)

## Entities

- Teams `T_1..T_n`. Every round = one case, released to all teams at once.
- A case has invoice lines `i = 1..m`. Each line has hidden values:
  - `t_i ≥ 0`: fair-value threshold, the max gross line total a claims expert accepts. `t_i = 0` if the line is **not covered** by the policy (and, per the rules, an unrelated line fails the same way: fraud for any `a > 0`).
  - `c_i`: payment cap, `c_i ≥ 4·t_i` and `≥` some undisclosed absolute floor. Shared across teams.
- Each team submits per line: `a_i` (charge price, handyman role) and `b_i` (acceptance limit, insurer role). Default `0/0` if omitted.

## Settlement

For every ordered pair (H = issuer, I = reviewer), H ≠ I, and every line:

```
if a_H <= b_I:                       # accepted
    pay = a_H         if a_H <= t else min(a_H, c)
else:                                # rejected
    pay = 1.5 * a_H   if a_H <= t else 0
I pays `pay` to H
```

Team net payoff = Σ received as H − Σ paid as I, over all opponents, lines and games.
The game is zero-sum across teams. Boundary cases: `a == t` counts as fair, and `a == b` counts as accepted.

## Worked example (from GAME_DESCRIPTION, t = 100)

| Team | a | b |
|---|---|---|
| Alpha | 100 | 130 |
| Beta | 150 | 90 |
| Delta | 100 | 110 |

Alpha→Beta: fair, rejected → Beta pays 150. Alpha→Delta: fair, accepted → 100.
Delta→Alpha: 100. Delta→Beta: 150. Beta→Alpha: 150 > 130, rejected, fraud → 0.
Beta→Delta: 0. Net: Alpha +150, Delta +150, Beta −300.
(The Deep Dive slides use a variant with Beta a = 120, which Alpha accepts: Alpha +30, Delta +150, Beta −180.)

## Consequences

- As H with `a ≤ t`: income ≥ `a` from every opponent (1.5·a from the strict ones). Income rises with `a` up to `t`.
- As H with `a > t`: income only from opponents with `b ≥ a`, capped at `c`.
- As I: the cost depends only on the incoming `a` and our `b`, never on other insurers.
- Omitting lines is never neutral: it means `b = 0`, which wrongly rejects every fair bill.
- Teams that join mid-tournament only play games that start after they were created.
