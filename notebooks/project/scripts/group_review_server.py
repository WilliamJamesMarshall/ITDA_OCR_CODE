"""Local pair review for product-group candidates; no annotation/fold mutations."""
import argparse
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from scripts import ocr_annotations as ann
from scripts.prepare_group_splits import OUT

def serve(port=8768):
    pairs=ann.read(OUT/'candidate_pairs.json');known={p['pair_id']:p for p in pairs}
    ids={p[k] for p in pairs for k in ('a','b')};token=secrets.token_urlsafe(32);lock=threading.Lock()
    decisions=OUT/'pair_decisions.json'
    if not decisions.exists():ann.write(decisions,{})
    class Handler(BaseHTTPRequestHandler):
        def send(self,value,status=200,kind='application/json'):
            data=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode()
            self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
        def do_GET(self):
            try:
                if self.path=='/':
                    html=(ann.ROOT/'notebooks/project/scripts/group_review.html').read_text(encoding='utf-8').replace('__TOKEN__',token)
                    return self.send(html.encode(),kind='text/html; charset=utf-8')
                if self.path=='/api/data':return self.send(dict(pairs=pairs,decisions=ann.read(decisions)))
                if self.path.startswith('/image/'):
                    image_id=self.path.split('/')[-1]
                    if image_id not in ids:return self.send(dict(error='Unknown image'),404)
                    r=ann.read(ann.record_path(image_id))
                    with ann.Image.open(ann.source_path(r)) as image:
                        image=image.convert('RGB');image.thumbnail((1400,1400));buffer=ann.io.BytesIO();image.save(buffer,format='JPEG',quality=90)
                    return self.send(buffer.getvalue(),kind='image/jpeg')
                self.send(dict(error='Not found'),404)
            except (ValueError,KeyError,FileNotFoundError) as exc:self.send(dict(error=str(exc)),400)
        def do_POST(self):
            if self.path!='/api/decision':return self.send(dict(error='Not found'),404)
            if self.headers.get('X-Review-Token')!=token:return self.send(dict(error='Invalid token'),403)
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<10000:raise ValueError('Invalid request size')
                payload=json.loads(self.rfile.read(size))
                key=payload['pair_id'];decision=payload['decision'];reviewer=payload['reviewer'].strip()
                if key not in known or decision not in ('same','different','uncertain') or not reviewer:raise ValueError('Invalid pair/decision/reviewer')
                with lock:
                    current=ann.read(decisions)
                    ann.write(OUT/'decision_history'/f'{ann.now().replace(":","-")}.json',dict(pair_id=key,before=current.get(key)))
                    current[key]=dict(decision=decision,reviewer=reviewer,recorded_at=ann.now(),method='explicit_pair_review')
                    ann.write(decisions,current)
                self.send(current[key])
            except (ValueError,KeyError,TypeError) as exc:self.send(dict(error=str(exc)),400)
        def log_message(self,*args):pass
    print(f'Group review: http://127.0.0.1:{port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8768);serve(parser.parse_args().port)
