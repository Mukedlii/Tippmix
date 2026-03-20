#!/usr/bin/env python3
import requests

r = requests.get(
    'https://api.github.com/repos/Mukedlii/Tippmix/actions/runs?per_page=5',
    headers={'Accept': 'application/vnd.github+json'}
)

data = r.json()
if 'workflow_runs' not in data:
    print(f"Error: {r.status_code}")
    print(data)
    exit(1)

runs = data['workflow_runs']

print("\nLast 5 workflow runs:")
print("="*60)

for run in runs[:5]:
    name = run['name']
    status = run['status']
    conclusion = run.get('conclusion', 'running')
    created = run['created_at'][:16].replace('T', ' ')
    
    icon = "✅" if conclusion == "success" else "❌" if conclusion == "failure" else "🔄"
    
    print(f"{icon} {name}")
    print(f"   Status: {status} | Conclusion: {conclusion}")
    print(f"   Created: {created}")
    print()
