import requests
import zipfile
import io

token = "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"
run_id = 23337266805  # Latest Reddit run

print(f"Downloading Reddit logs for run {run_id}...")

logs_url = f"https://api.github.com/repos/Mukedlii/Tippmix/actions/runs/{run_id}/logs"
log_resp = requests.get(logs_url, headers={'Authorization': f'token {token}'})

if log_resp.status_code == 200:
    z = zipfile.ZipFile(io.BytesIO(log_resp.content))
    z.extractall("reddit_logs")
    print("Logs extracted to reddit_logs/")
    
    # Show the main log
    main_log = "reddit_logs/reddit-consensus/3_Fetch Reddit consensus.txt"
    try:
        with open(main_log, 'r', encoding='utf-8') as f:
            content = f.read()
            print("\n" + "="*60)
            print("REDDIT CONSENSUS OUTPUT:")
            print("="*60)
            print(content[-2000:])  # Last 2000 chars
    except:
        print("Could not read log file")
else:
    print(f"Failed: {log_resp.status_code}")
