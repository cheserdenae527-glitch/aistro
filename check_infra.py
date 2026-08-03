import subprocess, sys, socket

r = subprocess.run([sys.executable, "-m", "pip", "list"], capture_output=True, text=True)
for line in r.stdout.splitlines():
    for kw in ["celery", "redis", "rq"]:
        if kw in line.lower():
            print(line)

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
result = s.connect_ex(("localhost", 6379))
print("Redis port 6379:", "OPEN" if result == 0 else "CLOSED")
s.close()
