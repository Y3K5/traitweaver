"""JSON-lines test bridge to actual handlers; no sockets, servers or file writes."""
import json
import sys
from unittest.mock import patch

from traitweaver import study, workspace_server
from traitweaver.completed_cycle import CompletedCycle
from test_review_handlers import MemoryConnection, MemoryServer


def main():
    with patch('socket.socket',side_effect=AssertionError('No sockets')):
        cycle=CompletedCycle.from_file('data/synthetic-cycle/REVIEW_PACKAGE.json')
        server=workspace_server.make_server(cycle,server_factory=MemoryServer)
        for line in sys.stdin:
            data=json.loads(line);body=data.get('body','');headers={'Host':'127.0.0.1:8765','Origin':'http://127.0.0.1:8765',**data.get('headers',{})}
            raw=body.encode();headers['Content-Length']=str(len(raw))
            wire=(data.get('method','GET')+' '+data['path']+' HTTP/1.0\r\n'+''.join(k+': '+v+'\r\n' for k,v in headers.items())+'\r\n').encode()+raw
            conn=MemoryConnection(wire);server.RequestHandlerClass(conn,('127.0.0.1',1000),server)
            head,payload=bytes(conn.response).split(b'\r\n\r\n',1);code=int(head.split(b' ')[1]);text=payload.decode()
            value=json.loads(text) if b'application/json' in head else None
            print(json.dumps({'ok':code<400,'status':code,'payload':value,'text':text}),flush=True)


if __name__=='__main__':main()
