"""Interactive API example; password and session token are never printed or saved."""
import argparse
import getpass
import json
import urllib.error
import urllib.request
import urllib.parse


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--url', default='http://localhost:8080')
    p.add_argument('--user', required=True)
    p.add_argument('--json', default=None, help='Non-secret JSON request body')
    p.add_argument('method', choices=['GET', 'POST', 'PUT'])
    p.add_argument('path')
    args = p.parse_args()
    if not args.path.startswith('/v1/') or '?' in args.url or '#' in args.url:
        p.error('Use a server base URL and a /v1/ API path')
    url = args.url.rstrip('/')
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1')):
        p.error('HTTPS required except for loopback')
    if parsed.username or parsed.password or parsed.path or args.path.startswith('/v1/auth/'):
        p.error('Use a bare server origin and a non-auth API path; login/logout are automatic')
    def call(path, method, data=None, token=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        req = urllib.request.Request(url + path, data=json.dumps(data).encode() if data is not None else None, headers=headers, method=method)
        # Do not follow redirects carrying Authorization to another origin.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(req, timeout=15) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    token = None
    try:
        login = call('/v1/auth/login', 'POST', {'username': args.user, 'password': getpass.getpass('Password: ')})
        token = login['accessToken']
        result = call(args.path, args.method, json.loads(args.json) if args.json else None, token)
        print(json.dumps(result, indent=2))
    except urllib.error.HTTPError as e:
        print('HTTP', e.code)
        raise SystemExit(1)
    finally:
        if token:
            try:
                call('/v1/auth/logout', 'POST', token=token)
            except (urllib.error.URLError, TimeoutError):
                pass


if __name__ == '__main__':
    main()
