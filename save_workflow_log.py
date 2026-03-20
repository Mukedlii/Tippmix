import requests
import zipfile
import io

GITHUB_TOKEN = "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"
REPO = "Mukedlii/Tippmix"

headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

runs_url = f"https://api.github.com/repos/{REPO}/actions/runs?per_page=1"
r = requests.get(runs_url, headers=headers)
run = r.json()['workflow_runs'][0]

logs_url = run['logs_url']
r = requests.get(logs_url, headers=headers)

z = zipfile.ZipFile(io.BytesIO(r.content))

for name in z.namelist():
    if 'morning' in name.lower() and 'Run bot' in name:
        content = z.read(name).decode('utf-8', errors='ignore')
        
        with open('workflow_log_bot_run.txt', 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"Saved to: workflow_log_bot_run.txt")
        print(f"Size: {len(content)} bytes")
        
        # Extract DEBUG and odds lines
        debug_lines = [line for line in content.split('\n') if '[DEBUG]' in line or 'ODDS' in line or 'odds' in line]
        
        print(f"\nFound {len(debug_lines)} DEBUG/odds lines")
        print("\nLast 50 lines with DEBUG/odds:")
        for line in debug_lines[-50:]:
            try:
                print(line)
            except:
                print(line.encode('ascii', errors='ignore').decode())
