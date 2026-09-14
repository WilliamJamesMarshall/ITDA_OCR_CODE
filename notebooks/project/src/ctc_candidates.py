"""Bounded CTC prefix search for diagnostics, never automatic digit correction."""
import math
import numpy as np


def candidates(probabilities, characters, blank=0, beam_width=4, token_top_k=3, max_steps=160):
    p = np.asarray(probabilities)
    if (p.ndim != 2 or not 0 < len(p) <= max_steps or p.shape[1] != len(characters)
            or not np.isfinite(p).all() or (p < 0).any() or (p > 1).any()
            or not np.allclose(p.sum(axis=1), 1., atol=.02)):
        return []
    if not 1 <= beam_width <= 8 or not 1 <= token_top_k <= 5:
        raise ValueError('Bounded CTC search configuration required')
    neg = -math.inf
    beams = {(): (0., neg)}
    def add(table, prefix, slot, score):
        pair = list(table.get(prefix, (neg, neg)))
        pair[slot] = float(np.logaddexp(pair[slot], score))
        table[prefix] = tuple(pair)
    for row in p:
        top = set(np.argsort(row)[-token_top_k:].tolist()) | {blank}
        next_beams = {}
        for prefix, (pb, pn) in beams.items():
            total = float(np.logaddexp(pb, pn))
            # Include repeated last token to preserve CTC prefix probability.
            for token in top | ({prefix[-1]} if prefix else set()):
                score = math.log(max(float(row[token]), 1e-30))
                if token == blank:
                    add(next_beams, prefix, 0, total + score)
                elif prefix and token == prefix[-1]:
                    add(next_beams, prefix, 1, pn + score)
                    add(next_beams, prefix + (token,), 1, pb + score)
                else:
                    add(next_beams, prefix + (token,), 1, total + score)
        beams = dict(sorted(next_beams.items(), key=lambda pair: float(np.logaddexp(*pair[1])),
                            reverse=True)[:beam_width])
    return [dict(text=''.join(characters[t] for t in prefix),
                 log_probability=float(np.logaddexp(*scores)), calibrated=False)
            for prefix, scores in sorted(beams.items(), key=lambda pair: float(np.logaddexp(*pair[1])), reverse=True)]
