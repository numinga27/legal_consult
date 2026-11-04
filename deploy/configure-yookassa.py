"""Run on the server as numinga. Read credentials from stdin, never argv/logs.

Input JSON: shop_id, secret_key. This tool validates /me, then stores credentials
with checkout disabled until receipt settings and notifications are confirmed.
"""
import base64
import json
import os
from pathlib import Path
import re
import shlex
import tempfile
from urllib.error import URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler


def main():
    import sys
    values=json.loads(sys.stdin.read(4096))
    shop=str(values['shop_id']);secret=values['secret_key'].strip()
    if not shop.isdecimal() or not 20 <= len(secret) <= 300 or any(c.isspace() for c in secret):
        raise ValueError('Invalid credential shape')
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    request=Request('https://api.yookassa.ru/v3/me',headers={
        'Authorization':'Basic '+base64.b64encode((shop+':'+secret).encode()).decode()})
    with build_opener(NoRedirect).open(request,timeout=15) as response:
        raw=response.read(100001)
        if len(raw)>100000:raise ValueError('Unexpected response size')
        account=json.loads(raw)
    if str(account.get('account_id')) != shop:
        raise ValueError('Shop mismatch')
    target=Path('/home/numinga/.config/legal-consult/app.env')
    if target.is_symlink() or not target.is_file() or target.stat().st_uid != os.getuid():
        raise ValueError('Expected existing private environment owned by current user')
    updates={'PAYMENT_PROVIDER':'yookassa','YOOKASSA_SHOP_ID':shop,'YOOKASSA_SECRET_KEY':secret,
             'YOOKASSA_ENABLED':'0','YOOKASSA_TEST':'1' if account.get('test') is True else '0'}
    lines=[line for line in target.read_text().splitlines() if not any(
        re.match(r'^(?:export\s+)?'+key+r'\s*=',line) for key in updates)]
    lines += [key+'='+shlex.quote(value) for key,value in updates.items()]
    fd,name=tempfile.mkstemp(prefix='.yookassa-env-',dir=target.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w') as output:
            output.write('\n'.join(lines)+'\n');output.flush();os.fsync(output.fileno())
        os.replace(name,target)
    finally:
        if os.path.exists(name):os.unlink(name)
    print(json.dumps({'credentials_saved':True,'shop_id':shop,'checkout_enabled':False,
        'status':account.get('status'),'test':account.get('test'),
        'fiscalization':account.get('fiscalization'),'fiscalization_enabled':account.get('fiscalization_enabled')},ensure_ascii=False))


if __name__=='__main__':
    try:main()
    except Exception:
        print('YooKassa configuration failed; credentials were not printed. Verify network, key and file permissions.')
        raise SystemExit(1) from None
