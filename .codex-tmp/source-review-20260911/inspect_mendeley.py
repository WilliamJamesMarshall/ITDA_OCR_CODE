import collections
import io
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen
import zipfile

sys.stdout.reconfigure(encoding='utf-8')
ROOT = Path(__file__).resolve().parent
FILE = json.loads((ROOT / 'mendeley_files.json').read_text())[0]

class RemoteZip(io.RawIOBase):
    def __init__(self):
        self.position = 0
        self.size = FILE['size']

    def seek(self, offset, whence=0):
        self.position = offset if whence == 0 else self.position + offset if whence == 1 else self.size + offset
        return self.position

    def tell(self):
        return self.position

    def read(self, size=-1):
        size = self.size - self.position if size < 0 else min(size, self.size - self.position)
        if size <= 0:
            return b''
        if size > 20_000_000:
            raise ValueError('Sample request exceeds 20 MB')
        req = Request(FILE['content_details']['download_url'], headers={'Range': f'bytes={self.position}-{self.position+size-1}', 'User-Agent': 'ITDA-dataset-review/1.0'})
        with urlopen(req, timeout=30) as response:
            if response.status != 206:
                raise RuntimeError('Server did not honor Range')
            data = response.read(size)
        self.position += len(data)
        return data

if __name__ == '__main__':
    with zipfile.ZipFile(RemoteZip()) as archive:
        entries = archive.infolist()
        records = [{'name': f.filename, 'size': f.file_size, 'compressed': f.compress_size} for f in entries if not f.is_dir()]
        (ROOT / 'mendeley_zip_index.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
        print('files', len(records))
        print('extensions', dict(collections.Counter(Path(f['name']).suffix.lower() for f in records)))
        print('directories', dict(collections.Counter(str(Path(f['name']).parent).replace('\\', '/') for f in records)))
        text_files = [f for f in records if Path(f['name']).suffix.lower() in {'.txt', '.json', '.csv', '.md'}]
        print('annotation files', json.dumps(text_files[:35], ensure_ascii=False))
        print('first files', json.dumps(records[:8], ensure_ascii=False))
        for entry in text_files[:12]:
            if entry['size'] < 8_000_000:
                data = archive.read(entry['name'])
                path = ROOT / ('mendeley_' + entry['name'].replace('/', '__').replace('\\', '__'))
                path.write_bytes(data)
                print('annotation sample', entry['name'], data.decode('utf-8', errors='replace')[:2200])
