"""Decode every admitted crop and audit shuffled weights without model/optimizer."""
import json
import os
import sys
from pathlib import Path
from collections import Counter


def main():
    run=Path(os.environ['ITDA_CUMULATIVE_RUN']).resolve()
    from scripts.train_cumulative_1_5 import validate_release,read,write
    from scripts.operating_environment import limit_cpu
    limit_cpu([0,1,2,3])
    release,config,pool=validate_release()
    sys.path.insert(0,release['runtime'])
    import paddle
    from ppocr.data import build_dataloader
    from ppocr.utils.logging import get_logger
    from scripts.weighted_cumulative_loss import attach_weights
    from scripts.train_cumulative_1_5 import remove_sampler_padding
    from scripts import weighted_cumulative_loss
    manifest=read(release['weight_manifest'])
    loader=build_dataloader(config,'Train',paddle.CPUPlace(),get_logger(),seed=20260911)
    sampler=remove_sampler_padding(loader.batch_sampler,3316)
    attach_weights(loader.dataset,manifest)
    # Synchronous precheck avoids Paddle's background reader hanging on a
    # rejected crop. It does not load an OCR model or update any parameters.
    for index in range(3316):
        try:
            loader.dataset[(320,48,index,None)]
        except BaseException as error:
            write(run/'weighted-loader-failure.json',dict(index=index,error=repr(error),
                data_line=loader.dataset.data_lines[loader.dataset.data_idx_order_list[index]].decode('utf-8')))
            raise
    seen=set();batches=Counter();sums=Counter()
    for batch in loader:
        ids=batch[6].numpy().tolist();weights=batch[5].numpy().tolist()
        assert len(ids)==len(set(ids)) and not seen.intersection(ids)
        seen.update(ids);batches[len(ids)]+=1
        for index,weight in zip(ids,weights):
            entry=manifest['entries'][index]
            assert abs(weight-entry['scaled_weight'])<1e-12
            sums[entry['round']]+=entry['coefficient']
    assert seen==set(range(3316)) and batches=={8:414,4:1}
    write(run/'weighted-loader-check.json',dict(status='passed',unique_crops=len(seen),batches=dict(batches),
        coefficient_sums=dict(sums),sampler=sampler,model_loaded=False,optimizer_executed=False))
    print(json.dumps(dict(status='passed',crops=len(seen),batches=dict(batches),coefficients=dict(sums))))


if __name__=='__main__':main()
