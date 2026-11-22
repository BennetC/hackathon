"""The pooled formula (fitted on games 1-29, worst-case selection, walk-forward checked):
   a = k x median fair, k = 0.92 if sources agree (cv < 0.15), 0.84 if they partly disagree (cv < 0.40), else 1.16
   b = 1.04 x lowest fair.   Applied to every line, using all available sources' fair estimates."""
import statistics
K_AGREE, K_SOME, K_DISAGREE, M_MIN = 0.92, 0.84, 1.16, 1.04
def line_ab(fairs):
    fv = [float(x) for x in fairs if x is not None]
    if not fv: return 0.0, 0.0
    mu = statistics.mean(fv); cv = statistics.pstdev(fv) / mu if mu > 0 else 0.0
    k = K_AGREE if cv < 0.15 else (K_SOME if cv < 0.40 else K_DISAGREE)
    return round(k * statistics.median(fv), 2), round(M_MIN * min(fv), 2)
def formula_ab(answers):
    """answers: {source: [line dicts with index, fair_gross_total]} -> {line: (a, b)}"""
    valid = [a for a in answers.values() if a]
    if not valid: return {}
    return {i + 1: line_ab([a[i]["fair_gross_total"] for a in valid if len(a) > i]) for i in range(max(len(a) for a in valid))}
