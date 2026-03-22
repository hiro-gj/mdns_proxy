import threading
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import socketserver

class mDNSProxyAPIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/merged-records':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            with self.server.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT hostname, ip_address, record_type, ttl FROM merged_records')
                records = [
                    {"hostname": row[0], "ip_address": row[1], "record_type": row[2], "ttl": row[3]}
                    for row in cursor.fetchall()
                ]
            
            self.wfile.write(json.dumps(records).encode())
        else:
            self.send_error(404, "File Not Found")

    def do_POST(self):
        if self.path == '/api/other-records':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            # トークン認証(簡易)
            auth_header = self.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Token '):
                self.send_error(401, "Unauthorized")
                return
            
            token = auth_header.split(' ')[1]
            try:
                data = json.loads(post_data)
                
                # DB更新
                with self.server.db.get_connection() as conn:
                    cursor = conn.cursor()
                    # 外部プロキシIDの取得/登録
                    cursor.execute('SELECT proxy_id FROM other_proxies WHERE token = ?', (token,))
                    row = cursor.fetchone()
                    if row:
                        proxy_id = row[0]
                    else:
                        cursor.execute(
                            'INSERT INTO other_proxies (ip_address, token, discovery_method) VALUES (?, ?, ?)',
                            (self.client_address[0], token, 'token')
                        )
                        proxy_id = cursor.lastrowid
                    
                    for record in data.get('records', []):
                        cursor.execute(
                            '''
                            INSERT INTO other_records (source_proxy_id, hostname, ip_address, record_type, ttl)
                            VALUES (?, ?, ?, ?, ?)
                            ''',
                            (proxy_id, record['hostname'], record['ip_address'], record.get('record_type', 'A'), record.get('ttl', 120))
                        )
                    conn.commit()

                self.send_response(201)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode())

            except Exception as e:
                self.send_error(400, f"Bad Request: {str(e)}")
        else:
            self.send_error(404, "Not Found")

from logger_config import logger

def start_server(db, port=80):
    try:
        server = HTTPServer(('', port), mDNSProxyAPIHandler)
        server.db = db
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        logger.info(f"[API Server] Listening on port {port}...")
        return server
    except Exception as e:
        logger.error(f"[API Server] Failed to start: {e}")
        return None
