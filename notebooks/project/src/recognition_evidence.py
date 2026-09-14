"""Read-only CTC evidence adapter for the installed PaddleX recognizer.

The original decoder remains authoritative. Unknown layouts/reordered strings
fail closed to missing evidence, never guessed character alignment.
"""
import numpy as np
from .ctc_candidates import candidates


class CTCEvidence:
    def __init__(self, decoder, collect_candidates=False):
        self.decoder = decoder
        self.rows = []
        self.collect_candidates = collect_candidates
        self.candidate_rows = []

    def __call__(self, pred, *args, **kwargs):
        output = self.decoder(pred, *args, **kwargs)
        texts = output[0]
        records = [() for _ in texts]
        alternatives = [[] for _ in texts]
        try:
            probabilities = np.asarray(pred[0])
            if probabilities.ndim != 3 or probabilities.shape[0] != len(texts):
                raise ValueError('Unknown CTC shape')
            for row, expected in enumerate(texts):
                indices = probabilities[row].argmax(axis=-1)
                chosen = np.ones(len(indices), dtype=bool)
                chosen[1:] = indices[1:] != indices[:-1]
                for token in self.decoder.get_ignored_tokens():
                    chosen &= indices != token
                positions = np.flatnonzero(chosen)
                decoded = ''.join(self.decoder.character[indices[p]] for p in positions)
                if decoded == expected and len(decoded) == len(positions):
                    records[row] = tuple(float(probabilities[row,p,indices[p]]) for p in positions)
                    # Only uncertain, mostly numeric crops receive bounded search.
                    # Retain output unchanged; alternatives need independent validation.
                    if (self.collect_candidates and records[row] and min(records[row]) < .8
                            and sum(c.isdigit() for c in decoded) >= 4
                            and len(decoded) <= 32 and list(self.decoder.get_ignored_tokens()) == [0]):
                        alternatives[row] = candidates(probabilities[row], self.decoder.character)
        except (AttributeError, ValueError, IndexError, TypeError):
            pass
        self.rows.extend(zip(texts, records))
        self.candidate_rows.extend(alternatives)
        return output
