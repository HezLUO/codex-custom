# Initial trusted Windows loader; no administrator access or shell policy changes.
$ErrorActionPreference = 'Stop'
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'Python 3.9+ is required; install Python and retry.' }
& $python.Source -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.9+ is required.' }
$loader = @'
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

def check(url, allow_query=False):
    p = urllib.parse.urlsplit(url)
    if (not p.hostname or p.username or p.password or (p.query and not allow_query) or p.fragment
            or p.scheme not in ('http', 'https')
            or (p.scheme == 'http' and p.hostname not in ('localhost', '127.0.0.1', '::1'))):
        raise ValueError('Loader must use HTTPS or an explicit loopback test URL')

class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check(newurl, allow_query=True)
        if req.full_url.startswith('https:') and not newurl.startswith('https:'):
            raise ValueError('Loader HTTPS redirect cannot downgrade transport')
        return super().redirect_request(req, fp, code, msg, headers, newurl)

url = os.environ.get('CODEX_CUSTOM_BOOTSTRAP_URL', 'https://raw.githubusercontent.com/HezLUO/codex-custom/main/bootstrap.py')
try:
    check(url)
    with tempfile.TemporaryDirectory(prefix='codex-custom-loader-') as temporary:
        path = Path(temporary) / 'bootstrap.py'
        with urllib.request.build_opener(Redirect()).open(url, timeout=30) as response:
            data = response.read(256 * 1024 + 1)
            if len(data) > 256 * 1024:
                raise ValueError('Loader exceeds size limit')
            length = response.headers.get('Content-Length')
            if length is not None and int(length) != len(data):
                raise ValueError('Loader download was interrupted')
        path.write_bytes(data)
        result = subprocess.run([sys.executable, str(path), *sys.argv[1:]])
        sys.exit(result.returncode)
except Exception:
    print('Installation stopped: bootstrap download failed; check source and network; use official codex for recovery', file=sys.stderr)
    sys.exit(1)
'@
$loader | & $python.Source - @args
if ($LASTEXITCODE -ne 0) { throw 'Installation stopped; use official codex for recovery.' }
