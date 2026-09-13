"""Link the 22 missing-original cases to existing product photos, for reference only."""
import argparse
import shutil
from pathlib import Path
from scripts.prepare_sequential_rounds import ROOT, read, write, csv_read, csv_write, digest
from scripts.grouped_plan import BASE, verify, validate_product_reference
from scripts.grouped_rounds import exclusive, now, evidence, checked_evidence


def link(base,source):
    verify(base)
    items=read(source)['items']
    index={item['test_id']:item for item in items}
    if len(items)!=22 or len(index)!=22:raise ValueError('Expected exactly 22 reviewed missing-original cases')
    with exclusive(base/'locks/metadata.lock'):
        if (base/'locks/execution.lock').exists():raise ValueError('Wait for active execution before metadata changes')
        verify(base)
        rows=csv_read(base/'test_to_original_mapping.csv')
        before={r['test_id']:dict(r) for r in rows}
        if any(r.get('product_reference_path') for r in rows if r['test_id'] in index):
            raise ValueError('References already exist; do not rewrite reviewed history')
        revision=base/'mapping_revisions'/('product-references-'+now().replace(':','-'))
        revision.mkdir(parents=True)
        for name in ('test_to_original_mapping.csv','mapping_review_queue.csv','manifest_lock.json'):
            shutil.copy2(base/name,revision/name)
        linked=[]
        for row in rows:
            if row['test_id'] not in index:continue
            item=index[row['test_id']]
            checked_evidence(item['history']);checked_evidence(item['deletion_list'])
            if row['mapping_status']!='source_identified_file_missing':raise ValueError('Not a missing-original case')
            product=(ROOT/item['prior_confirmation']['a']).resolve()
            test=ROOT/'테스트용데이터'/(row['test_id']+product.suffix)
            if digest(test)!=row['test_sha256']:raise ValueError('Test image changed')
            proof=dict(created_at=now(),test_id=row['test_id'],round=int(row['round']),reference_path=str(product),
                sha256=digest(product),source=evidence(source),history=item['history'],
                relationship='byte_identical_existing_product_copy',training_authorized=False,
                user_instruction='그러면 원본파일이 부재한 22장은 해당되는 기존 상품사진과 연결해.',
                instruction_scope='Existing product reference linkage only; not training approval')
            path=revision/'proofs'/(row['test_id']+'.json');write(path,proof)
            row.update(product_reference_path=str(product),product_reference_sha256=proof['sha256'],
                product_reference_kind='augmented_existing_product',product_reference_usage='reference_only',
                product_reference_proof_path=str(path),product_reference_proof_sha256=digest(path),
                mapping_issue='Existing product reference linked; augmented copy is not a training original')
            validate_product_reference(row)
            linked.append(dict(test_id=row['test_id'],round=int(row['round']),product_path=str(product)))
        if len(linked)!=22:raise ValueError('Incomplete product references')
        for row in rows:
            if row['test_id'] not in index and row!=before[row['test_id']]:raise ValueError('Unrelated mapping changed')
        csv_write(base/'test_to_original_mapping.csv',rows,list(dict.fromkeys(k for row in rows for k in row)))
        queue=[dict(test_id=r['test_id'],round=r['round'],reason=r.get('mapping_issue') or 'Original review required') for r in rows if not r['original_id']]
        csv_write(base/'mapping_review_queue.csv',queue,['test_id','round','reason'])
        lock=read(base/'manifest_lock.json')
        for name in ('test_to_original_mapping.csv','mapping_review_queue.csv'):lock[name]=digest(base/name)
        write(base/'manifest_lock.json',lock)
        result=dict(created_at=now(),linked=linked,count=22,training_authorized=False,revision=str(revision),verification=verify(base))
        write(revision/'change.json',result)
        write(base/'existing_product_references.json',result)
        return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',type=Path,default=BASE)
    p.add_argument('--source',type=Path,required=True)
    a=p.parse_args();print(link(a.workspace,a.source))


if __name__=='__main__':main()
