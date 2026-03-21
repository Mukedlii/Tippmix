import requests
import os

token = "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"
r = requests.get(
    'https://api.github.com/repos/Mukedlii/Tippmix/actions/runs',
    headers={'Authorization': f'token {token}'}
)

runs = r.json()['workflow_runs'][:5]
print("\n=== LATEST WORKFLOW RUNS ===")
for run in runs:
    print(f"{run['name']}")
    print(f"  Status: {run['status']} | Conclusion: {run['conclusion']}")
    print(f"  Created: {run['created_at']}")
    print(f"  URL: {run['html_url']}")
    print()
