"""Read-only CTC evidence adapter for the installed PaddleX recognizer.

The original decoder remains authoritative. Unknown layouts/reordered strings
fail closed to missing evidence, never guessed character alignment.
"""
import numpy as np


class CTCEvidence:
    def __init__(self, decoder):
        self.decoder = decoder
        self.rows = []

    def __call__(self, pred, *args, **kwargs):
        output = self.decoder(pred, *args, **kwargs)
        texts = output[0]
        records = [() for _ in texts]
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
        except (AttributeError, ValueError, IndexError, TypeError):
            pass
        self.rows.extend(zip(texts, records))
        return output
