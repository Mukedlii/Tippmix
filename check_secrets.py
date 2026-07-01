import os
import requests

token = (os.getenv("GITHUB_TOKEN") or "").strip()
if not token:
    raise RuntimeError("GITHUB_TOKEN environment variable is required.")

r = requests.get(
    'https://api.github.com/repos/Mukedlii/Tippmix/actions/secrets',
    headers={
        'Authorization': 'token ' + token,
        'Accept': 'application/vnd.github+json'
    }
)

secrets = [s['name'] for s in r.json()['secrets']]
print('GitHub Secrets:')
for s in secrets:
    print(f'  - {s}')

print(f'\nODDS_API_KEY exists: {"ODDS_API_KEY" in secrets}')
