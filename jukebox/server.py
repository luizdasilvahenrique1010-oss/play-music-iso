#!/usr/bin/env python3
"""Servidor local do Play Musica (ISO).
Serve o jukebox em http://127.0.0.1:8765 e detecta pendrives/HDs sozinho."""
import os, re, json, mimetypes, subprocess, threading, unicodedata
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

APP = os.environ.get('JUKEBOX_DIR', os.path.dirname(os.path.abspath(__file__)))
PORT = int(os.environ.get('JUKEBOX_PORT', '8765'))
MNT = os.environ.get('JUKEBOX_MNT', '/mnt/jukebox')
MEDIA = {'.mp3', '.wav', '.ogg', '.oga', '.m4a', '.aac', '.flac', '.opus', '.wma', '.mp4', '.m4v', '.webm',
         '.mkv', '.mov', '.avi', '.mpg', '.mpeg', '.3gp', '.ogv', '.wmv', '.jpg', '.jpeg', '.png', '.webp',
         '.gif', '.bmp'}
SKIP = {'$recycle.bin', 'system volume information', 'lost+found', '.trash', '.trashes', 'recycler',
        'windows', 'program files', 'proc', 'sys'}
FS_OK = {'vfat', 'exfat', 'ntfs', 'ext2', 'ext3', 'ext4', 'btrfs', 'xfs', 'f2fs'}
mimetypes.add_type('audio/mpeg', '.mp3')
mimetypes.add_type('audio/mp4', '.m4a')
mimetypes.add_type('audio/ogg', '.opus')
mimetypes.add_type('image/webp', '.webp')
mimetypes.add_type('video/x-matroska', '.mkv')

state = {'root': APP, 'id': 'local'}
lock = threading.Lock()


def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').lower()


def human(n):
    n = float(n or 0)
    for u in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024:
            return ('%.0f %s' if u in ('B', 'KB', 'MB') else '%.1f %s') % (n, u)
        n /= 1024
    return '%.1f PB' % n


def find_dir(root, wanted):
    try:
        for d in os.listdir(root):
            if norm(d) == wanted and os.path.isdir(os.path.join(root, d)):
                return d
    except OSError:
        pass
    return None


def has_files(path):
    for _, _, fs in os.walk(path):
        for f in fs:
            if os.path.splitext(f)[1].lower() in MEDIA and not f.startswith('._'):
                return True
    return False


def walk_media(base, root, out, limit=200000):
    for dp, dns, fns in os.walk(base):
        dns[:] = sorted(d for d in dns if not d.startswith('.') and d.lower() not in SKIP)
        for f in sorted(fns):
            if f.startswith('.') or os.path.splitext(f)[1].lower() not in MEDIA:
                continue
            out.append(os.path.relpath(os.path.join(dp, f), root).replace(os.sep, '/'))
            if len(out) >= limit:
                return


def scan_list(root, is_local=False):
    out = []
    m = find_dir(root, 'musicas')
    if m:
        walk_media(os.path.join(root, m), root, out)
        i = find_dir(root, 'imagem')
        if i:
            walk_media(os.path.join(root, i), root, out)
    elif not is_local:
        walk_media(root, root, out)
    return out


def local_has():
    m = find_dir(APP, 'musicas')
    return bool(m and has_files(os.path.join(APP, m)))


def ensure_mount(dev, fstype, name):
    target = os.path.join(MNT, re.sub(r'[^A-Za-z0-9_.-]', '_', name))
    if os.path.ismount(target):
        return target
    os.makedirs(target, exist_ok=True)
    if fstype == 'ntfs':
        tries = [('ntfs-3g', 'ro'), ('ntfs3', 'ro,iocharset=utf8')]
    elif fstype == 'vfat':
        tries = [('vfat', 'ro,iocharset=utf8')]
    else:
        tries = [(fstype, 'ro')]
    for typ, opts in tries:
        try:
            r = subprocess.run(['mount', '-t', typ, '-o', opts, dev, target], capture_output=True, timeout=25)
            if r.returncode == 0:
                return target
        except Exception:
            pass
    return None


def truthy(v):
    return v in (True, 1, '1', 'true')


def lsblk_nodes():
    try:
        r = subprocess.run(['lsblk', '-J', '-b', '-o',
                            'NAME,PATH,LABEL,FSTYPE,SIZE,MOUNTPOINTS,TYPE,RM,TRAN,MODEL'],
                           capture_output=True, timeout=10, text=True)
        data = json.loads(r.stdout)
    except Exception:
        return []
    res = []

    def rec(n, tran, model, rm):
        tran = n.get('tran') or tran
        model = (n.get('model') or model or '').strip()
        rm = rm or truthy(n.get('rm'))
        kids = n.get('children') or []
        if n.get('type') in ('part', 'disk', 'crypt', 'lvm') and not kids:
            res.append((n, tran, model, rm))
        for k in kids:
            rec(k, tran, model, rm)

    for n in data.get('blockdevices', []):
        if n.get('type') in ('loop', 'rom', 'ram'):
            continue
        rec(n, None, None, False)
    return res


def fontes():
    out = [{'id': 'local', 'nome': 'Sistema (local)', 'tipo': 'local',
            'detalhe': 'Músicas gravadas neste sistema', 'temMusicas': local_has()}]
    with lock:
        for n, tran, model, rm in lsblk_nodes():
            fs = (n.get('fstype') or '').lower()
            size = int(n.get('size') or 0)
            label = n.get('label') or ''
            if fs not in FS_OK or size < 64 * 1024 * 1024 or label.upper() in ('VTOYEFI', 'EFI', 'ESP'):
                continue
            mps = [m for m in (n.get('mountpoints') or []) if m]
            mp = None
            for m in mps:
                if m.startswith(('/media', '/mnt', '/run/media', '/run/live/medium')):
                    mp = m
                    break
            if mp is None and not mps:
                mp = ensure_mount(n['path'], fs, n['name'])
            if not mp:
                continue
            tem = bool(find_dir(mp, 'musicas'))
            if '/run/live/medium' in mp and not tem:
                continue
            tipo = 'usb' if (rm or tran == 'usb') else 'hd'
            out.append({'id': n['name'], 'nome': label or model or n['name'], 'tipo': tipo,
                        'detalhe': '%s · %s · %s' % (human(size), fs.upper(), n['name']),
                        'temMusicas': tem, '_mp': mp})
    return out


def carregar(fid):
    if fid == 'local':
        state.update(root=APP, id='local')
        return scan_list(APP, True)
    for f in fontes():
        if f['id'] == fid and '_mp' in f:
            state.update(root=f['_mp'], id=fid)
            return scan_list(f['_mp'])
    return None


def biblioteca_js():
    ext = [f for f in fontes() if f['tipo'] != 'local' and f['temMusicas']]
    lst = []
    if not ext and local_has():
        state.update(root=APP, id='local')
        lst = scan_list(APP, True)
    return 'window.BIBLIOTECA=' + json.dumps(lst) + ';'


def resolve(rel):
    variants = [rel, unicodedata.normalize('NFC', rel), unicodedata.normalize('NFD', rel)]
    for root in (state['root'], APP):
        root = os.path.realpath(root)
        for v in variants:
            fp = os.path.realpath(os.path.join(root, v))
            if (fp == root or fp.startswith(root + os.sep)) and os.path.isfile(fp):
                return fp
    return None


class H(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'PlayMusica'

    def log_message(self, *a):
        pass

    def send_bytes(self, body, ctype, code=200):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def send_json(self, obj, code=200):
        self.send_bytes(json.dumps(obj).encode(), 'application/json; charset=utf-8', code)

    def send_file(self, fp):
        size = os.path.getsize(fp)
        start, end, code = 0, size - 1, 200
        rng = self.headers.get('Range')
        if rng:
            m = re.match(r'bytes=(\d*)-(\d*)', rng)
            if m:
                a, b = m.groups()
                if a == '' and b:
                    start = max(0, size - int(b))
                elif a:
                    start = int(a)
                    if b:
                        end = min(int(b), size - 1)
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header('Content-Range', 'bytes */%d' % size)
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                code = 206
        ctype = mimetypes.guess_type(fp)[0] or 'application/octet-stream'
        if ctype.startswith('text/') or ctype.endswith('javascript'):
            ctype += '; charset=utf-8'
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(end - start + 1))
        if code == 206:
            self.send_header('Content-Range', 'bytes %d-%d/%d' % (start, end, size))
        self.end_headers()
        if self.command == 'HEAD':
            return
        with open(fp, 'rb') as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(65536, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        try:
            u = urlparse(self.path)
            p = unquote(u.path)
            if p == '/api/fontes':
                return self.send_json([{k: v for k, v in f.items() if not k.startswith('_')} for f in fontes()])
            if p == '/api/carregar':
                lst = carregar(parse_qs(u.query).get('id', [''])[0])
                if lst is None:
                    return self.send_json({'erro': 'fonte nao encontrada'}, 404)
                return self.send_json({'lista': lst})
            if p == '/biblioteca.js':
                return self.send_bytes(biblioteca_js().encode(), 'application/javascript; charset=utf-8')
            fp = resolve(p.lstrip('/') or 'index.html')
            if not fp:
                return self.send_bytes(b'nao encontrado', 'text/plain; charset=utf-8', 404)
            self.send_file(fp)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            try:
                self.send_bytes(str(e).encode(), 'text/plain; charset=utf-8', 500)
            except Exception:
                pass


class S(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == '__main__':
    os.makedirs(MNT, exist_ok=True)
    S(('127.0.0.1', PORT), H).serve_forever()
