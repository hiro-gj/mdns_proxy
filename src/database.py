import os
import sqlite3

class Database:
    def __init__(self):
        # src/ の親ディレクトリ（mdns_proxy/）の db/ ディレクトリを基準にする
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.db_path = os.path.join(base_dir, 'db', 'mdns_proxy.sqlite3')
        # ディレクトリが存在しない場合は作成
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # static_hosts
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS static_hosts (
                    host_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hostname TEXT NOT NULL UNIQUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # self_records
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS self_records (
                    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hostname TEXT NOT NULL,
                    ip_address TEXT NOT NULL,
                    record_type TEXT NOT NULL,
                    ttl INTEGER NOT NULL,
                    resolution_method TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # other_proxies
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS other_proxies (
                    proxy_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_address TEXT NOT NULL UNIQUE,
                    token TEXT NOT NULL,
                    discovery_method TEXT NOT NULL,
                    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            # other_records
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS other_records (
                    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_proxy_id INTEGER NOT NULL,
                    hostname TEXT NOT NULL,
                    ip_address TEXT NOT NULL,
                    record_type TEXT NOT NULL,
                    ttl INTEGER NOT NULL,
                    received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(source_proxy_id) REFERENCES other_proxies(proxy_id)
                )
            ''')
            # merged_records
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS merged_records (
                    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hostname TEXT NOT NULL,
                    ip_address TEXT NOT NULL,
                    record_type TEXT NOT NULL,
                    ttl INTEGER NOT NULL,
                    source_type TEXT NOT NULL,
                    source_record_id INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def sync_static_hosts(self, hosts_config):
        """search_hosts.ini の内容を static_hosts テーブルに同期する"""
        if not hosts_config.has_section('hosts'):
            return
            
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # DB上の既存ホストを取得
            cursor.execute('SELECT hostname FROM static_hosts')
            existing_hosts = set(row[0] for row in cursor.fetchall())
            
            # INIファイルのホストを取得
            ini_hosts = set(hosts_config.options('hosts'))
            
            # INIにあってDBにないものを追加
            for host in ini_hosts:
                if host not in existing_hosts:
                    cursor.execute(
                        'INSERT INTO static_hosts (hostname) VALUES (?)',
                        (host,)
                    )
            
            # DBにあってINIにないものを削除
            for host in existing_hosts:
                if host not in ini_hosts:
                    cursor.execute(
                        'DELETE FROM static_hosts WHERE hostname = ?',
                        (host,)
                    )
            
            conn.commit()
