"""Original-balanced crop losses with fixed round-count coefficients.

No resampling: each admitted optimizer crop is consumed exactly once. The
fixed batch divisor also prevents the residual batch from doubling its weight.
"""
from collections import Counter, defaultdict
import math

ROUND_COUNTS = {1: 216, 2: 500, 3: 500, 4: 394, 5: 500}


def weight_manifest(pool):
    samples = [s for s in pool['samples'] if s['role'] == 'optimizer_train']
    crops_per_image = Counter(s['image_id'] for s in samples)
    images_by_round = defaultdict(set)
    for sample in samples:
        r = int(pool['admitted'][sample['image_id']]['round'])
        images_by_round[r].add(sample['image_id'])
    if set(images_by_round) != set(ROUND_COUNTS):
        raise ValueError('All five rounds need eligible training originals')
    entries = []
    for index, sample in enumerate(samples):
        image = sample['image_id']
        r = int(pool['admitted'][image]['round'])
        coefficient = ROUND_COUNTS[r] / sum(ROUND_COUNTS.values())
        coefficient /= len(images_by_round[r]) * crops_per_image[image]
        entries.append(dict(index=index, image_id=image, round=r,
            crop_path=sample['crop_path'], crop_sha256=sample['crop_sha256'],
            transcription=sample['transcription'], coefficient=coefficient,
            scaled_weight=len(samples)*coefficient))
    if len({e['crop_path'] for e in entries}) != len(entries):
        raise ValueError('Duplicate optimizer crop path')
    totals = {r: math.fsum(e['coefficient'] for e in entries if e['round']==r)
              for r in ROUND_COUNTS}
    for r, count in ROUND_COUNTS.items():
        if not math.isclose(totals[r], count/2110, abs_tol=1e-12):
            raise ValueError('Round coefficient mismatch')
    return dict(policy='round-original-count_then_eligible-original_then_crop-v1',
        round_counts=ROUND_COUNTS, eligible_originals={r:len(v) for r,v in images_by_round.items()},
        round_coefficient_sums=totals, crop_count=len(samples), fixed_batch_divisor=8,
        nrtr_reduction='nonpadding-token-mean-per-crop', entries=entries)


def attach_weights(dataset, manifest):
    """Bind metadata to the actual shuffled dataset line, never sampler position.

    The pinned dataset silently substitutes another crop on decode failure.
    Reject that recursion: a failed crop must not acquire another crop's weight.
    """
    import numpy as np
    by_path = {e['crop_path']: e for e in manifest['entries']}
    if dataset.need_reset or dataset.ds_width:
        raise ValueError('Weighted training requires the fixed single-scale dataset')
    actual = [line.decode('utf-8').rstrip('\r\n').split('\t') for line in dataset.data_lines]
    if len(actual) != len(by_path) or {x[0] for x in actual} != set(by_path):
        raise ValueError('Dataset differs from the weighted manifest')
    if any(len(x)!=2 or x[1]!=by_path[x[0]]['transcription'] for x in actual):
        raise ValueError('Dataset transcription mismatch')
    # File terminators are not label characters. Preserve the approved text,
    # including meaningful spaces; normalize only in-memory record delimiters.
    dataset.data_lines=[(x[0]+'\t'+x[1]+'\n').encode('utf-8') for x in actual]
    encoders=[op for op in dataset.ops if getattr(op,'gtc_encode_type',None)=='NRTRLabelEncode']
    if len(encoders)!=1 or encoders[0].ctc_encode.max_text_len!=25 or encoders[0].gtc_encode.max_text_len!=25:
        raise ValueError('Unexpected 25-character label contract')
    # NRTR's array includes BOS/EOS whereas CTC's limit counts printed chars.
    # Keep CTC/model max_text_length=25; reserve two extra label-array slots.
    encoders[0].gtc_encode.max_text_len=27
    original_type = type(dataset)

    class WeightedDataset(original_type):
        def __getitem__(self, properties):
            if getattr(self, '_weighted_loading', False):
                raise RuntimeError('Crop failure: silent dataset substitution rejected')
            self._weighted_loading = True
            try:
                line = self.data_lines[self.data_idx_order_list[int(properties[2])]]
                entry = by_path[line.decode('utf-8').split('\t', 1)[0]]
                result = super().__getitem__(properties)
                if len(result) != 5:
                    raise RuntimeError('Unexpected weighted dataset contract')
                return list(result) + [np.float64(entry['scaled_weight']), np.int64(entry['index'])]
            finally:
                self._weighted_loading = False

    dataset.__class__ = WeightedDataset


def nrtr_per_crop(prediction, batch):
    """Same 0.1 label smoothing as pinned NRTRLoss; mean within each crop."""
    import paddle
    import paddle.nn.functional as F
    max_len = int(batch[3].max().item())
    target = batch[2][:, 1:2+max_len]
    if list(prediction.shape[:2]) != list(target.shape):
        raise ValueError('NRTR prediction/target shape mismatch')
    log_prob = F.log_softmax(prediction, axis=-1)
    chosen = paddle.take_along_axis(log_prob, target.unsqueeze(-1), axis=-1).squeeze(-1)
    eps = 0.1
    token_loss = -(1-eps)*chosen - eps/(prediction.shape[-1]-1)*(log_prob.sum(-1)-chosen)
    mask = (target != 0).astype(token_loss.dtype)
    lengths = mask.sum(-1)
    if bool((lengths == 0).any().item()):
        raise ValueError('NRTR crop without nonpadding targets')
    return (token_loss*mask).sum(-1)/lengths


def build_weighted_loss(manifest, output):
    import json
    import paddle
    from paddle import nn

    class OriginalWeightedLoss(nn.Layer):
        def __init__(self):
            super().__init__()
            self.ctc = nn.CTCLoss(blank=0, reduction='none')
            self.seen = set()
            self.rounds = {r:dict(crops=0, coefficient_sum=0., ctc_sum=0., nrtr_sum=0.,
                                  weighted_ctc=0., weighted_nrtr=0.) for r in ROUND_COUNTS}

        def forward(self, prediction, batch):
            if len(batch)!=7:
                raise ValueError('Missing original/crop weight metadata')
            indices = [int(i) for i in batch[6].numpy().tolist()]
            if len(indices)!=len(set(indices)) or self.seen.intersection(indices):
                raise RuntimeError('Repeated optimizer crop')
            if any(i<0 or i>=len(manifest['entries']) for i in indices):
                raise ValueError('Unknown optimizer crop index')
            entries = [manifest['entries'][i] for i in indices]
            weights = batch[5].astype(prediction['ctc'].dtype)
            for supplied,e in zip(batch[5].numpy().tolist(),entries):
                if not math.isclose(supplied,e['scaled_weight'],rel_tol=1e-10):
                    raise ValueError('Weight/index mismatch')
            ctc_pred = prediction['ctc'].transpose((1,0,2))
            input_lengths = paddle.to_tensor([ctc_pred.shape[0]]*len(indices),dtype='int64')
            ctc = self.ctc(ctc_pred,batch[1].astype('int32'),input_lengths,batch[3].astype('int64'))
            nrtr = nrtr_per_crop(prediction['gtc'],batch)
            if not bool(paddle.isfinite(ctc).all().item()) or not bool(paddle.isfinite(nrtr).all().item()):
                raise RuntimeError('Non-finite recognition loss')
            weighted_ctc = (ctc*weights).sum()/manifest['fixed_batch_divisor']
            weighted_nrtr = (nrtr*weights).sum()/manifest['fixed_batch_divisor']
            self.seen.update(indices)
            ctc_values,nrtr_values = ctc.numpy().tolist(),nrtr.numpy().tolist()
            for e,c,n in zip(entries,ctc_values,nrtr_values):
                values=self.rounds[e['round']];q=e['coefficient']
                values['crops']+=1;values['coefficient_sum']+=q
                values['ctc_sum']+=c;values['nrtr_sum']+=n
                values['weighted_ctc']+=q*c;values['weighted_nrtr']+=q*n
            with output.open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(dict(indices=indices,scaled_weights=[e['scaled_weight'] for e in entries],
                    ctc=ctc_values,nrtr=nrtr_values,divisor=manifest['fixed_batch_divisor']))+'\n')
            return dict(loss=weighted_ctc+weighted_nrtr,CTCLoss=weighted_ctc,NRTRLoss=weighted_nrtr)

        def finish(self):
            if self.seen != set(range(manifest['crop_count'])):
                raise RuntimeError('Weighted epoch has missing crops')
            for r,count in ROUND_COUNTS.items():
                if not math.isclose(self.rounds[r]['coefficient_sum'],count/2110,abs_tol=1e-10):
                    raise RuntimeError('Consumed round weights differ from approval')
            return dict(unique_crops=len(self.seen),rounds=self.rounds,
                        coefficient_sum=sum(v['coefficient_sum'] for v in self.rounds.values()),
                        loss_scope='online training losses, not frozen-model evaluation')

    return OriginalWeightedLoss()
