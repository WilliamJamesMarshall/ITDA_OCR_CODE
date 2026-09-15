"""One-shot postprocessing for the running approved epoch. No OCR/training calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime,timezone


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--release-sha',required=True)
    parser.add_argument('--finalizer',type=Path,required=True)
    parser.add_argument('--finalizer-sha',required=True)
    args=parser.parse_args();run=args.run.resolve()
    def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    if sha(run/'release/release.json')!=args.release_sha or sha(args.finalizer)!=args.finalizer_sha:
        raise ValueError('Postprocessing binding mismatch')
    claim=run/'postprocess.claim'
    with claim.open('x',encoding='utf-8') as stream:stream.write(str(os.getpid()))
    status=dict(status='waiting_for_supervisor',pid=os.getpid(),started_at=datetime.now(timezone.utc).isoformat(),
        release_sha256=args.release_sha,finalizer_sha256=args.finalizer_sha,
        full_image_tests=False,additional_training=False,shared_weights_changed=False)
    def publish():
        temp=run/'postprocess-status.tmp'
        temp.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temp,run/'postprocess-status.json')
    publish()
    try:
        deadline=time.monotonic()+12*60*60
        while not (run/'supervisor-result.json').is_file():
            if time.monotonic()>deadline:raise TimeoutError('Supervisor result absent after 12 hours; no restart attempted')
            time.sleep(5)
        supervisor=json.loads((run/'supervisor-result.json').read_text(encoding='utf-8-sig'))
        if supervisor['status']!='completed' or supervisor.get('exit_code')!=0:
            raise RuntimeError('Training/supervisor failed; preserving evidence without retry')
        if sha(args.finalizer)!=args.finalizer_sha:raise ValueError('Finalizer changed')
        status['status']='auditing_completed_training';publish()
        with (run/'postprocess.log').open('x',encoding='utf-8') as log:
            subprocess.run([sys.executable,str(args.finalizer),'--run',str(run)],
                           check=True,stdout=log,stderr=subprocess.STDOUT)
        status['status']='report_completed_tests_held'
    except BaseException as error:
        status.update(status='postprocess_failed',error=repr(error))
        raise
    finally:
        status['finished_at']=datetime.now(timezone.utc).isoformat();publish()


if __name__=='__main__':main()
