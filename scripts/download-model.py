import socket, urllib.request, pathlib, json, hashlib, shutil, argparse
parser = argparse.ArgumentParser(description="Download verified Ollama model layers from the official registry. Optional DNS hint affects only this process.")
parser.add_argument("--registry-ip", default=None)
args = parser.parse_args()
import ipaddress
if args.registry_ip: ipaddress.ip_address(args.registry_ip)
original=socket.getaddrinfo
def resolve(host, port, *args, **kwargs):
    return original(args.registry_ip if args.registry_ip and host=='registry.ollama.ai' else host,port,*args,**kwargs)
socket.getaddrinfo=resolve
root=pathlib.Path(__file__).resolve().parents[1]/'.local/models'
blobs=root/'blobs'; blobs.mkdir(parents=True,exist_ok=True)
with urllib.request.urlopen('https://registry.ollama.ai/v2/library/qwen3.5/manifests/4b-q4_K_M', timeout=30) as response:
    raw = response.read()
manifest=json.loads(raw)
for entry in [manifest['config']]+manifest['layers']:
    digest=entry['digest']; path=blobs/digest.replace(':','-')
    if path.exists() and hashlib.file_digest(path.open('rb'),'sha256').hexdigest()==digest.split(':')[1]:
        continue
    temporary=path.with_suffix('.partial')
    print('Downloading',digest,entry['size'],flush=True)
    with urllib.request.urlopen('https://registry.ollama.ai/v2/library/qwen3.5/blobs/'+digest,timeout=120) as response, temporary.open('wb') as out:
        shutil.copyfileobj(response,out,1024*1024)
    with temporary.open('rb') as f: actual=hashlib.file_digest(f,'sha256').hexdigest()
    if actual!=digest.split(':')[1]: raise RuntimeError('Hash mismatch '+digest)
    temporary.replace(path)
    print('Verified',digest,flush=True)
target=root/'manifests/registry.ollama.ai/library/qwen3.5/4b-q4_K_M'
target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(raw)
print('Manifest SHA256',hashlib.sha256(raw).hexdigest(),flush=True)
