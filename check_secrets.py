import requests

r = requests.get(
    'https://api.github.com/repos/Mukedlii/Tippmix/actions/secrets',
    headers={
        'Authorization': 'Bearer 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',
        'Accept': 'application/vnd.github+json'
    }
)

secrets = [s['name'] for s in r.json()['secrets']]
print('GitHub Secrets:')
for s in secrets:
    print(f'  - {s}')

print(f'\nODDS_API_KEY exists: {"ODDS_API_KEY" in secrets}')
