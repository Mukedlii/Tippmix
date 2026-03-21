import requests
import zipfile
import io

token = "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"
run_id = 23361162176  # 21:23 run

print(f"Downloading logs for run {run_id}...")

logs_url = f"https://api.github.com/repos/Mukedlii/Tippmix/actions/runs/{run_id}/logs"
log_resp = requests.get(logs_url, headers={'Authorization': f'token {token}'})

if log_resp.status_code == 200:
    z = zipfile.ZipFile(io.BytesIO(log_resp.content))
    z.extractall("workflow_logs_21_23")
    print("Logs extracted to workflow_logs_21_23/")
    print("Files:")
    for name in z.namelist():
        print(f"  {name}")
else:
    print(f"Failed: {log_resp.status_code}")
