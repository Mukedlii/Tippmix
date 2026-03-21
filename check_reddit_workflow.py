import requests

token = "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"

r = requests.get(
    'https://api.github.com/repos/Mukedlii/Tippmix/actions/runs',
    headers={'Authorization': f'token {token}'},
    params={'per_page': 50}
)

runs = r.json()['workflow_runs']

# Filter Reddit runs
reddit_runs = [x for x in runs if 'Reddit' in x['name']]

print(f"Reddit workflow runs (last {len(reddit_runs)}):\n")

for run in reddit_runs[:10]:
    status = run['status']
    conclusion = run['conclusion']
    created = run['created_at'][:16].replace('T', ' ')
    
    print(f"  {created} | {status:10s} | {conclusion or 'running':10s}")
    print(f"    {run['html_url']}")
    print()
