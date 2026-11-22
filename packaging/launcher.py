import os
import sys
import threading
import webbrowser
from pathlib import Path

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from werkzeug.serving import BaseWSGIServer
from web.app import app


class LocalServer(BaseWSGIServer):
    # Windows can otherwise let two launchers bind the same address.
    allow_reuse_address = False


def main():
    server = None
    for port in range(5000, 5021):
        try:
            server = LocalServer('127.0.0.1', port, app)
            break
        except (OSError, SystemExit):
            continue
    if server is None:
        print('端口 5000–5020 均不可用，请释放端口后重试。')
        input('按回车退出。')
        return
    url = f'http://127.0.0.1:{port}/'
    print(f'服务地址：{url}\n关闭此窗口或按 Ctrl+C 退出。')
    if os.environ.get('MUSICRECO_NO_BROWSER') != '1':
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__': main()
