import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
from scripts.resolve_original_derivatives import compare
from scripts.refine_derivative_photometry import reconstruct
from scripts.grouped_plan import revise_mapping, validate_product_reference
from scripts.sequential_rounds import build_admission
from scripts.prepare_sequential_rounds import write, read, csv_write, csv_read, digest


class DerivativeGeometryTests(unittest.TestCase):
    def test_existing_product_reference_does_not_become_training_original(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);product=root/'상품사진입니다/000896.jpg'
            product.parent.mkdir();product.write_bytes(b'synthetic augmented product')
            proof=root/'proof.json'
            write(proof,dict(test_id='AMLT000896',reference_path=str(product.resolve()),sha256=digest(product),training_authorized=False))
            row=dict(test_id='AMLT000896',round='4',original_id='',augmented='true',test_sha256=digest(product),
                product_reference_path=str(product),product_reference_sha256=digest(product),
                product_reference_usage='reference_only',product_reference_kind='augmented_existing_product',
                product_reference_proof_path=str(proof),product_reference_proof_sha256=digest(proof))
            with patch('scripts.grouped_plan.ROOT',root):
                validate_product_reference(row)
                for fields in ({'original_id':'AMLC000896'},{'augmented':'false'},
                               {'product_reference_usage':'optimizer_train'},{'test_sha256':'wrong'}):
                    with self.assertRaises(ValueError): validate_product_reference({**row,**fields})
            with self.assertRaises(ValueError): build_admission([row],4,{}, {})

    def test_brightness_clipping_reconstruction_and_negative_control(self):
        rng=np.random.default_rng(94)
        original=cv2.GaussianBlur(rng.integers(0,256,(640,640),dtype=np.uint8),(3,3),0)
        matrix=np.eye(3)
        shifted=np.clip(original.astype(float)+40,0,255).astype(np.uint8)
        proof=reconstruct(original,shifted,matrix)
        self.assertTrue(proof['strong'],proof)
        self.assertAlmostEqual(proof['offset'],40,delta=1)
        different=np.roll(shifted,20,axis=0)
        self.assertFalse(reconstruct(original,different,matrix)['strong'])

    def feature(self, image, name):
        points,desc=cv2.SIFT_create(nfeatures=650).detectAndCompute(image,None)
        return dict(path=name,desc=desc,points=np.float32([p.pt for p in points]),size=image.shape[::-1])

    def test_rotated_same_frame_is_recognized_and_unrelated_frame_is_not(self):
        rng=np.random.default_rng(15)
        original=cv2.GaussianBlur(rng.integers(15,240,(640,640),dtype=np.uint8),(7,7),0)
        for i in range(80):
            x,y=rng.integers(20,620,2)
            cv2.circle(original,(int(x),int(y)),int(rng.integers(3,18)),int(rng.integers(20,230)),-1)
        matrix=cv2.getRotationMatrix2D((320,320),8,.95)
        derived=cv2.warpAffine(original,matrix,(640,640))
        other=rng.integers(15,240,(640,640),dtype=np.uint8)
        images=dict(original=original,derived=derived,other=other)
        with patch('scripts.resolve_original_derivatives.gray',side_effect=images.__getitem__):
            match=compare(self.feature(original,'original'),self.feature(derived,'derived'))
            self.assertIsNotNone(match)
            self.assertTrue(match['strong'],match)
            unrelated=compare(self.feature(original,'original'),self.feature(other,'other'))
            self.assertTrue(unrelated is None or not unrelated['strong'])

    def test_revision_preserves_previous_link_and_backs_up_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);base=root/'workflow';base.mkdir()
            original=root/'학습대상데이터/AMLC000001.jpg';original.parent.mkdir()
            original.write_bytes(b'synthetic original fixture')
            annotation=root/'annotation.json'
            write(annotation,dict(review=dict(status='approved'),image_sha256=digest(original)))
            fixed=dict(test_id='AMLT000001',round='1',legacy_round='1',test_sha256='fixed',
                       augmented='false',seen_in_development='true',original_id='AMLC000001')
            pending=dict(test_id='AMLT000859',round='4',legacy_round='3',test_sha256='derivative',
                         augmented='true',seen_in_development='false',original_id='')
            fields=list(fixed)
            csv_write(base/'test_to_original_mapping.csv',[fixed,pending],fields)
            csv_write(base/'mapping_review_queue.csv',[dict(test_id=pending['test_id'])],['test_id'])
            write(base/'manifest_lock.json',{})
            updated=dict(pending,original_id=original.stem,original_path=str(original),original_sha256=digest(original),
                         annotation_path=str(annotation),annotation_sha256=digest(annotation))
            proof=root/'proof.json'
            write(proof,dict(relationship='derived_from',reviewer='synthetic test',source_reference='fixture',
                  reviewed_at='2026-09-13T12:00:00+09:00',
                  **{k:updated[k] for k in ('test_id','original_id','test_sha256','original_sha256')}))
            updated.update(mapping_review_path=str(proof),mapping_review_sha256=digest(proof))
            candidate=root/'candidate.csv'
            csv_write(candidate,[fixed,updated],list(dict.fromkeys([*fixed,*updated])))
            with patch('scripts.grouped_plan.ROOT',root),patch('scripts.grouped_plan.verify',return_value={}):
                revise_mapping(base,candidate)
            actual=csv_read(base/'test_to_original_mapping.csv')
            self.assertTrue(all(actual[0][k]==v for k,v in fixed.items()))
            self.assertEqual(actual[1]['original_id'],original.stem)
            backup=next((base/'mapping_revisions').iterdir())
            self.assertEqual(csv_read(backup/'test_to_original_mapping.csv')[1]['original_id'],'')
            self.assertEqual(csv_read(base/'mapping_review_queue.csv'),[])
            self.assertEqual(read(base/'manifest_lock.json')['test_to_original_mapping.csv'],digest(base/'test_to_original_mapping.csv'))


if __name__=='__main__': unittest.main()
