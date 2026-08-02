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
            
            with self.server.db.connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT hostname, ip_address, record_type, ttl FROM merged_records')
                records = [
                    {"hostname": row[0], "ip_address": row[1], "record_type": row[2], "ttl": row[3]}
                    for row in cursor.fetchall()
                ]
            
            self.wfile.write(json.dumps(records).encode())
        else:
            self.send_error(404, "File Not Found")

    def _get_node_id_from_token(self, token):
        # Token format: mDNSProxy_<hostname>_<node_id>
        parts = token.split('_')
        if len(parts) >= 3:
            return parts[-1]
        return None

    def do_POST(self):
        import scheduler
        
        # 自ノードIDの取得
        my_node_id = scheduler._get_node_id(self.server.sys_config)

        if self.path == '/api/other-records':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            # トークン認証(簡易)
            auth_header = self.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Token '):
                self.send_error(401, "Unauthorized")
                return
            
            token = auth_header.split(' ')[1]
            
            # 送信元のノードIDとポートを取得
            sender_node_id = self.headers.get('X-Sender-Node-ID')
            if not sender_node_id:
                sender_node_id = self._get_node_id_from_token(token)
                
            sender_port_str = self.headers.get('X-Sender-Port')
            try:
                sender_port = int(sender_port_str) if sender_port_str else 53080
            except ValueError:
                sender_port = 53080

            # 自ノード判定：自ノードからのPOSTは無視して成功レスポンス
            if sender_node_id and sender_node_id == my_node_id:
                self.send_response(201)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "Ignored self loopback"}).encode())
                return

            try:
                data = json.loads(post_data)
                import dns_resolver
                
                # DB更新
                with self.server.db.connection() as conn:
                    cursor = conn.cursor()
                    # 外部プロキシIDの取得/登録
                    proxy_id = None
                    
                    # 1. 最初に sender_node_id で検索する（node_id 制約違反を防止）
                    if sender_node_id:
                        cursor.execute('SELECT proxy_id FROM other_proxies WHERE node_id = ?', (sender_node_id,))
                        row = cursor.fetchone()
                        if row:
                            proxy_id = row[0]
                            cursor.execute(
                                '''
                                UPDATE other_proxies 
                                SET ip_address = ?, port = ?, token = ?, last_seen = CURRENT_TIMESTAMP, is_active = 1
                                WHERE proxy_id = ?
                                ''',
                                (self.client_address[0], sender_port, token, proxy_id)
                            )

                    # 2. sender_node_id でヒットしなかった場合、同一 IPアドレス・ポートでの検索を試みる
                    if not proxy_id:
                        cursor.execute(
                            '''
                            SELECT proxy_id FROM other_proxies 
                            WHERE ip_address = ? OR ip_address = ? OR ip_address LIKE ?
                            ''', 
                            (self.client_address[0], f"{self.client_address[0]}:{sender_port}", f"{self.client_address[0]}%")
                        )
                        ip_row = cursor.fetchone()
                        if ip_row:
                            proxy_id = ip_row[0]
                            cursor.execute(
                                '''
                                UPDATE other_proxies 
                                SET node_id = ?, ip_address = ?, port = ?, token = ?, last_seen = CURRENT_TIMESTAMP, is_active = 1
                                WHERE proxy_id = ?
                                ''',
                                (sender_node_id, self.client_address[0], sender_port, token, proxy_id)
                            )

                    # 3. それでもヒットしなかった場合、token で検索する
                    if not proxy_id:
                        cursor.execute('SELECT proxy_id FROM other_proxies WHERE token = ?', (token,))
                        row = cursor.fetchone()
                        if row:
                            proxy_id = row[0]
                            cursor.execute(
                                '''
                                UPDATE other_proxies 
                                SET node_id = ?, ip_address = ?, port = ?, last_seen = CURRENT_TIMESTAMP, is_active = 1
                                WHERE proxy_id = ?
                                ''',
                                (sender_node_id, self.client_address[0], sender_port, proxy_id)
                            )
                        else:
                            cursor.execute(
                                '''
                                INSERT INTO other_proxies (node_id, ip_address, port, token, discovery_method) 
                                VALUES (?, ?, ?, ?, ?)
                                ''',
                                (sender_node_id, self.client_address[0], sender_port, token, 'token')
                            )
                            proxy_id = cursor.lastrowid
                    
                    # 既存の other_records は、該当するプロキシから送られてきた最新のレコードで完全に上書き（置き換え）
                    cursor.execute('DELETE FROM other_records WHERE source_proxy_id = ?', (proxy_id,))
                    
                    for record in data.get('records', []):
                        # ループバックアドレスの除外
                        if dns_resolver.is_loopback(record['ip_address']):
                            continue
                        ttl_val = record.get('ttl')
                        if ttl_val is None or not isinstance(ttl_val, int) or ttl_val < 0:
                            ttl_val = 120
                        cursor.execute(
                            '''
                            INSERT INTO other_records (source_proxy_id, hostname, ip_address, record_type, ttl)
                            VALUES (?, ?, ?, ?, ?)
                            ''',
                            (proxy_id, record['hostname'], record['ip_address'], record.get('record_type', 'A'), ttl_val)
                        )
                    
                # 受信直後にマージ更新を実行
                scheduler._merge_records(self.server.db)

                self.send_response(201)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode())

            except Exception as e:
                self.send_error(400, f"Bad Request: {str(e)}")

        elif self.path == '/api/static-hosts':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            auth_header = self.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Token '):
                self.send_error(401, "Unauthorized")
                return
            
            token = auth_header.split(' ')[1]
            
            sender_node_id = self.headers.get('X-Sender-Node-ID')
            if not sender_node_id:
                sender_node_id = self._get_node_id_from_token(token)

            sender_port_str = self.headers.get('X-Sender-Port')
            try:
                sender_port = int(sender_port_str) if sender_port_str else 53080
            except ValueError:
                sender_port = 53080

            if sender_node_id and sender_node_id == my_node_id:
                self.send_response(201)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "Ignored self loopback"}).encode())
                return

            try:
                data = json.loads(post_data)
                
                with self.server.db.connection() as conn:
                    cursor = conn.cursor()
                    
                    # 外部プロキシIDの取得/登録（必要に応じて）
                    proxy_id = None
                    
                    # 1. 最初に sender_node_id で検索する（node_id 制約違反を防止）
                    if sender_node_id:
                        cursor.execute('SELECT proxy_id FROM other_proxies WHERE node_id = ?', (sender_node_id,))
                        row = cursor.fetchone()
                        if row:
                            proxy_id = row[0]
                            cursor.execute(
                                '''
                                UPDATE other_proxies 
                                SET ip_address = ?, port = ?, token = ?, last_seen = CURRENT_TIMESTAMP, is_active = 1
                                WHERE proxy_id = ?
                                ''',
                                (self.client_address[0], sender_port, token, proxy_id)
                            )

                    # 2. sender_node_id でヒットしなかった場合、同一 IPアドレス・ポートでの検索を試みる
                    if not proxy_id:
                        cursor.execute(
                            '''
                            SELECT proxy_id FROM other_proxies 
                            WHERE ip_address = ? OR ip_address = ? OR ip_address LIKE ?
                            ''', 
                            (self.client_address[0], f"{self.client_address[0]}:{sender_port}", f"{self.client_address[0]}%")
                        )
                        ip_row = cursor.fetchone()
                        if ip_row:
                            proxy_id = ip_row[0]
                            cursor.execute(
                                '''
                                UPDATE other_proxies 
                                SET node_id = ?, ip_address = ?, port = ?, token = ?, last_seen = CURRENT_TIMESTAMP, is_active = 1
                                WHERE proxy_id = ?
                                ''',
                                (sender_node_id, self.client_address[0], sender_port, token, proxy_id)
                            )

                    # 3. それでもヒットしなかった場合、token で検索する
                    if not proxy_id:
                        cursor.execute('SELECT proxy_id FROM other_proxies WHERE token = ?', (token,))
                        row = cursor.fetchone()
                        if row:
                            proxy_id = row[0]
                            cursor.execute(
                                '''
                                UPDATE other_proxies 
                                SET node_id = ?, ip_address = ?, port = ?, last_seen = CURRENT_TIMESTAMP, is_active = 1
                                WHERE proxy_id = ?
                                ''',
                                (sender_node_id, self.client_address[0], sender_port, proxy_id)
                            )
                        else:
                            cursor.execute(
                                '''
                                INSERT INTO other_proxies (node_id, ip_address, port, token, discovery_method) 
                                VALUES (?, ?, ?, ?, ?)
                                ''',
                                (sender_node_id, self.client_address[0], sender_port, token, 'token')
                            )

                    # 既存の static_hosts を取得
                    cursor.execute('SELECT hostname FROM static_hosts')
                    existing_hosts = set(r[0] for r in cursor.fetchall())
                    
                    for host_data in data.get('hosts', []):
                        hostname = host_data.get('hostname')
                        if hostname and hostname not in existing_hosts:
                            cursor.execute(
                                'INSERT INTO static_hosts (hostname) VALUES (?)',
                                (hostname,)
                            )
                            existing_hosts.add(hostname)

                self.send_response(201)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode())

            except Exception as e:
                self.send_error(400, f"Bad Request: {str(e)}")

        else:
            self.send_error(404, "Not Found")

from logger_config import logger

def start_server(db, sys_config, port=80):
    import sys
    try:
        server = HTTPServer(('', port), mDNSProxyAPIHandler)
        server.db = db
        server.sys_config = sys_config
        
        # Pico(MicroPython)環境ではセカンドコア(core1)でのスレッド起動を完全に排除し、
        # メインループ内のシングルスレッドで非同期に協調動作させます。
        if sys.platform == 'rp2':
            # ソケットのバインドとノンブロッキング化(s.settimeout(0.01))のみ行います
            # ※ serve_forever() 内部に書かれているソケット初期化をここで行うか、
            # 特化メソッドを用意して呼び出します。
            s = HTTPServer.socket = None
            import usocket as socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('', port))
            s.listen(5)
            s.settimeout(0.01) # ノンブロッキング設定
            server.socket = s
            logger.info(f"[API Server] (Single-Core Non-blocking) Listening on port {port}...")
        else:
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()
            logger.info(f"[API Server] Listening on port {port}...")
        return server
    except Exception as e:
        logger.error(f"[API Server] Failed to start: {e}")
        return None
