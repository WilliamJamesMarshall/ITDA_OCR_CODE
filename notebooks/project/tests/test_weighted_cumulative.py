import math
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
import numpy as np
import paddle
from scripts.weighted_cumulative_loss import (
    ROUND_COUNTS,weight_manifest,attach_weights,nrtr_per_crop,build_weighted_loss)


def pool_fixture():
    pool=dict(samples=[],admitted={})
    for r in range(1,6):
        for i in range(2):
            image=f'r{r}i{i}'
            pool['admitted'][image]={'round':str(r)}
            for k in range(i+1):
                pool['samples'].append(dict(image_id=image,role='optimizer_train',
                    crop_path=f'{image}c{k}',crop_sha256='fixture',transcription='12'))
    return pool


class WeightedCumulativeTest(unittest.TestCase):
    def test_round_and_original_totals(self):
        m=weight_manifest(pool_fixture())
        self.assertAlmostEqual(sum(e['coefficient'] for e in m['entries']),1)
        self.assertAlmostEqual(sum(e['scaled_weight'] for e in m['entries']),15)
        for r,n in ROUND_COUNTS.items():
            for i in range(2):
                total=sum(e['coefficient'] for e in m['entries'] if e['image_id']==f'r{r}i{i}')
                self.assertAlmostEqual(total,n/2110/2)

    def test_missing_round_rejected(self):
        pool=pool_fixture();pool['samples']=[s for s in pool['samples'] if not s['image_id'].startswith('r5')]
        with self.assertRaises(ValueError):weight_manifest(pool)

    def test_actual_shuffled_dataset_binding_and_substitution_guard(self):
        m=weight_manifest(pool_fixture())
        class Dataset:
            need_reset=False;ds_width=False
            def __getitem__(self,properties):
                if getattr(self,'fail',False):return self.__getitem__(properties)
                return [0]*5
        d=Dataset();d.data_lines=[(e['crop_path']+'\t12\r\n').encode() for e in reversed(m['entries'])]
        d.ops=[SimpleNamespace(gtc_encode_type='NRTRLabelEncode',ctc_encode=SimpleNamespace(max_text_len=25),gtc_encode=SimpleNamespace(max_text_len=25))]
        d.data_idx_order_list=list(range(15));attach_weights(d,m)
        result=d[(320,48,0,None)]
        self.assertEqual(result[6],14)
        self.assertEqual(result[5],m['entries'][14]['scaled_weight'])
        self.assertEqual(d.ops[0].gtc_encode.max_text_len,27)
        self.assertEqual(d.ops[0].ctc_encode.max_text_len,25)
        self.assertNotIn(b'\r',d.data_lines[0])
        d.fail=True
        with self.assertRaises(RuntimeError):d[(320,48,0,None)]

    def test_nrtr_mean_matches_pinned_smoothing_per_crop_and_gradients(self):
        paddle.seed(13)
        pred=paddle.randn([2,3,5]);pred.stop_gradient=False
        batch=[None,None,paddle.to_tensor([[1,2,3,0],[1,2,3,4]]),paddle.to_tensor([2,2])]
        value=nrtr_per_crop(pred,batch)
        logp=paddle.nn.functional.log_softmax(pred,-1)
        expected=[]
        for i,target in enumerate([[2,3],[2,3,4]]):
            terms=[]
            for j,t in enumerate(target):
                terms.append(-0.9*logp[i,j,t]-0.1/4*(logp[i,j].sum()-logp[i,j,t]))
            expected.append(paddle.stack(terms).mean())
        self.assertTrue(np.allclose(value.numpy(),paddle.stack(expected).numpy(),rtol=1e-6))
        value.sum().backward()
        self.assertGreater(float(paddle.abs(pred.grad).sum()),0)
        self.assertTrue(np.allclose(pred.grad.numpy()[0,2],0))

    def test_both_heads_gradient_scaling_and_remainder_fixed_divisor(self):
        m=weight_manifest(pool_fixture())
        with tempfile.TemporaryDirectory() as temp:
            loss=build_weighted_loss(m,Path(temp)/'audit.jsonl')
            ctc=paddle.randn([2,5,5]);ctc.stop_gradient=False
            nrtr=paddle.randn([2,3,5]);nrtr.stop_gradient=False
            entries=m['entries'][:2]
            batch=[paddle.zeros([2,3,48,320]),paddle.to_tensor([[1,2],[1,2]]),
                paddle.to_tensor([[1,2,3,0],[1,2,3,0]]),paddle.to_tensor([2,2]),paddle.ones([2]),
                paddle.to_tensor([e['scaled_weight'] for e in entries],dtype='float64'),paddle.to_tensor([0,1])]
            result=loss(dict(ctc=ctc,gtc=nrtr),batch)
            base_ctc=paddle.nn.CTCLoss(blank=0,reduction='none')(ctc.transpose([1,0,2]),batch[1].astype('int32'),paddle.to_tensor([5,5]),batch[3])
            base_nrtr=nrtr_per_crop(nrtr,batch)
            w=batch[5].astype('float32')
            expected=((base_ctc+base_nrtr)*w).sum()/8
            self.assertAlmostEqual(float(result['loss']),float(expected),places=5)
            result['loss'].backward()
            self.assertTrue(np.isfinite(ctc.grad.numpy()).all())
            self.assertGreater(float(paddle.abs(ctc.grad).sum()),0)
            self.assertGreater(float(paddle.abs(nrtr.grad).sum()),0)
            with self.assertRaises(RuntimeError):loss(dict(ctc=ctc,gtc=nrtr),batch)
            with self.assertRaises(RuntimeError):loss.finish()


if __name__=='__main__':unittest.main()
