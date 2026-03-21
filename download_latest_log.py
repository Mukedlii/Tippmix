import requests
import zipfile
import io

token = "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"

# Get latest run
r = requests.get(
    'https://api.github.com/repos/Mukedlii/Tippmix/actions/runs',
    headers={'Authorization': f'token {token}'}
)
latest_run = r.json()['workflow_runs'][0]
run_id = latest_run['id']
print(f"Latest run ID: {run_id}")
print(f"Status: {latest_run['status']} | Conclusion: {latest_run['conclusion']}")

# Download logs
logs_url = f"https://api.github.com/repos/Mukedlii/Tippmix/actions/runs/{run_id}/logs"
log_resp = requests.get(logs_url, headers={'Authorization': f'token {token}'})

if log_resp.status_code == 200:
    # Extract zip
    z = zipfile.ZipFile(io.BytesIO(log_resp.content))
    z.extractall("workflow_logs")
    print("\nLogs extracted to workflow_logs/")
    print("Files:")
    for name in z.namelist():
        print(f"  {name}")
else:
    print(f"Failed to download logs: {log_resp.status_code}")
