"""Freeze Paddle BN running statistics without freezing affine parameters."""
import hashlib


class FrozenBatchNormStatistics:
    def __init__(self, model):
        import paddle

        kinds = tuple(getattr(paddle.nn, name) for name in
                      ('BatchNorm', 'BatchNorm1D', 'BatchNorm2D', 'BatchNorm3D', 'SyncBatchNorm'))
        self.layers = [(name, layer) for name, layer in model.named_sublayers(include_self=True)
                       if isinstance(layer, kinds)]
        if not self.layers:
            raise ValueError('No BatchNorm layers to freeze')
        # Explicit batch-stat overrides would defeat evaluation-mode freezing.
        if any(getattr(layer, '_use_global_stats', None) is False for _, layer in self.layers):
            raise ValueError('Explicit batch-statistics mode is not supported')
        self.initial_sha256 = self.fingerprint()
        self.handle = model.register_forward_pre_hook(self._before_forward)

    def _before_forward(self, model, inputs):
        # Layer.eval() also changes Paddle's global tracer. Set only the BN
        # mode, preserving the root's training path and affine gradients.
        # Reapply on every forward because root.train() recursively resets it.
        for _, layer in self.layers:
            layer.training = False

    def fingerprint(self):
        digest = hashlib.sha256()
        for name, layer in self.layers:
            for field in ('_mean', '_variance'):
                digest.update(f'{name}.{field}'.encode())
                digest.update(getattr(layer, field).numpy().tobytes())
        return digest.hexdigest()

    def assert_unchanged(self):
        if self.fingerprint() != self.initial_sha256:
            raise RuntimeError('Frozen BatchNorm statistics changed')

    def evidence(self):
        self.assert_unchanged()
        return {'layer_names': [name for name, _ in self.layers],
                'running_tensor_count': 2 * len(self.layers),
                'statistics_sha256': self.initial_sha256}


def validation_gate(candidate, baseline):
    """Independent non-regression checks; no metric can hide another's loss."""
    if candidate['sample_count'] != baseline['sample_count']:
        return False
    for current, prior in ((candidate, baseline),
                           (candidate['digit_metrics'], baseline['digit_metrics'])):
        if (current['sample_count'] != prior['sample_count']
                or current['ground_truth_character_count'] != prior['ground_truth_character_count']
                or current['exact_match_count'] < prior['exact_match_count']
                or current['edit_error_count'] > prior['edit_error_count']):
            return False
    from scripts.recognition_metrics import selection_key
    # Epoch is a tie-breaker, not a validation-quality measurement. Retain the
    # earlier checkpoint on ties when selecting, but allow a tied candidate
    # through the separately approved whole-image validation gate.
    return selection_key(candidate)[:3] >= selection_key(baseline)[:3]
