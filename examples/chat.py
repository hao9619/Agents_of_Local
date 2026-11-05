"""标准库 API 示例：修改 MODEL、options 和 messages 即可实验。"""
import json
import sys
import urllib.request

MODEL = 'local-coder-4060'
BASE = 'http://127.0.0.1:11435'


def request(path, body=None):
    data = None if body is None else json.dumps(body).encode('utf-8')
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=300) as response:
        return json.load(response)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    checking = '--check' in sys.argv
    payload = {'model': MODEL, 'stream': False, 'think': False,
               'options': {'num_ctx': 32768, 'num_predict': 8192, 'temperature': 0.2},
               'messages': [{'role': 'user', 'content': '用中文简短介绍你自己。'}]}
    if checking:
        print(json.dumps(request('/api/version')))
        payload['messages'] = [{'role': 'user', 'content':
            'Call deployment_probe with token="4060-check". Then report the exact output string. Do not guess its output.'}]
        payload['tools'] = [{'type': 'function', 'function': {
            'name': 'deployment_probe', 'description': 'Read a deployment verification token.',
            'parameters': {'type': 'object', 'properties': {'token': {'type': 'string'}},
                           'required': ['token']}}}]
    result = request('/api/chat', payload)
    print(json.dumps(result, ensure_ascii=False))
    if checking:
        calls = result['message'].get('tool_calls', [])
        if not calls or calls[0]['function']['name'] != 'deployment_probe':
            raise RuntimeError('Expected deployment_probe tool call')
        if calls[0]['function']['arguments'].get('token') != '4060-check':
            raise RuntimeError('Incorrect tool arguments')
        payload['messages'].extend([result['message'], {'role': 'tool',
            'tool_name': 'deployment_probe', 'content': 'DEPLOYMENT_OK_4060'}])
        result = request('/api/chat', payload)
        print(json.dumps(result, ensure_ascii=False))
        if 'DEPLOYMENT_OK_4060' not in result['message'].get('content', ''):
            raise RuntimeError('Model did not report the actual tool result')
        print('PASS: tool call and result round trip')
