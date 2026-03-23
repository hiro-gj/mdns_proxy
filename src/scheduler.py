import threading
import time
import dns_resolver

from logger_config import logger

def loop_task(db, sys_config):
    while True:
        try:
            logger.info("[Scheduler] Running periodic tasks...")
            
            # 1. 独自DNS名前解決（static_hosts -> self_records）
            dns_resolver.resolve_all(db, sys_config)

            # 2. プロキシ発見（固定IPから）
            _discover_proxies(db, sys_config)

            # 3. 自レコード(self_records)を他のプロキシに送信
            _sync_to_others(db, sys_config)

            # 4. マージ処理（self_records + other_records -> merged_records）
            _merge_records(db)

            # 5. TTL減算とクリーンアップ
            _cleanup_records(db)

        except Exception as e:
            logger.error(f"[Scheduler] Error: {e}")
        
        interval = int(sys_config.get('system', 'interval', fallback='30'))
        time.sleep(interval)

def start(db, sys_config):
    t = threading.Thread(target=loop_task, args=(db, sys_config), daemon=True)
    t.start()
    return t

def _discover_proxies(db, sys_config):
    # network セクションから external_proxies を取得し、other_proxies に登録する簡易実装
    if not sys_config.has_option('network', 'external_proxies'):
        return
    proxies = sys_config.get('network', 'external_proxies').split(',')
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        for proxy in proxies:
            proxy = proxy.strip()
            if not proxy: continue
            
            # IPとポートを分離 (ex: 192.168.1.10:8080 or 192.168.1.10)
            if ':' in proxy:
                ip, port = proxy.split(':', 1)
            else:
                ip = proxy
                port = '80'
                
            # TODO: dbのother_proxiesスキーマにport列があれば保存するが、現状ip_addressとして扱うか？
            # 一旦、ip_address列に「ip:port」の形式で保存するように変更する。（後続の通信処理でポート番号を利用できるように）
            # もしスキーマにportがないなら、ip_addressにコロン付きで登録しておく
            cursor.execute('SELECT proxy_id FROM other_proxies WHERE ip_address = ?', (proxy,))
            if not cursor.fetchone():
                cursor.execute(
                    'INSERT INTO other_proxies (ip_address, token, discovery_method) VALUES (?, ?, ?)',
                    (proxy, 'dummy_token', 'fixed')
                )
        conn.commit()

import urllib.request
import json

def _sync_to_others(db, sys_config):
    # self_records と static_hosts の内容を HTTP(POST) で other_proxies に送信する
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. self_records の取得
        cursor.execute('SELECT hostname, ip_address, record_type, ttl FROM self_records')
        records = []
        for row in cursor.fetchall():
            records.append({
                "hostname": row[0],
                "ip_address": row[1],
                "record_type": row[2],
                "ttl": row[3]
            })
            
        # 2. static_hosts の取得
        cursor.execute('SELECT hostname FROM static_hosts')
        static_hosts = []
        for row in cursor.fetchall():
            static_hosts.append({"hostname": row[0]})
        
        cursor.execute('SELECT ip_address FROM other_proxies')
        proxies = cursor.fetchall()
        
    if not proxies:
        return
        
    token_prefix = sys_config.get('system', 'token_prefix', fallback='mDNSProxy_')
    import socket
    token = f"{token_prefix}{socket.gethostname()}"
    
    # other-records 送信
    if records:
        data_records = json.dumps({"records": records}).encode('utf-8')
        for (proxy_ip,) in proxies:
            url = f"http://{proxy_ip}/api/other-records"
            req = urllib.request.Request(url, data=data_records, method='POST')
            req.add_header('Content-Type', 'application/json')
            req.add_header('Authorization', f'Token {token}')
            req.add_header('Content-Length', str(len(data_records)))
            
            try:
                with urllib.request.urlopen(req, timeout=5) as response:
                    pass
            except Exception as e:
                logger.error(f"[_sync_to_others] Failed to sync records with {proxy_ip}: {e}")

    # static-hosts 送信
    if static_hosts:
        data_hosts = json.dumps({"hosts": static_hosts}).encode('utf-8')
        for (proxy_ip,) in proxies:
            url = f"http://{proxy_ip}/api/static-hosts"
            req = urllib.request.Request(url, data=data_hosts, method='POST')
            req.add_header('Content-Type', 'application/json')
            req.add_header('Authorization', f'Token {token}')
            req.add_header('Content-Length', str(len(data_hosts)))
            
            try:
                with urllib.request.urlopen(req, timeout=5) as response:
                    pass
            except Exception as e:
                logger.error(f"[_sync_to_others] Failed to sync static_hosts with {proxy_ip}: {e}")

def _merge_records(db):
    with db.get_connection() as conn:
        cursor = conn.cursor()
        # 一旦全クリア
        cursor.execute('DELETE FROM merged_records')
        
        # self_records をコピー
        # 重複を排除するためGROUP BYを使用
        cursor.execute('''
            INSERT INTO merged_records (hostname, ip_address, record_type, ttl, source_type, source_record_id)
            SELECT hostname, ip_address, record_type, MAX(ttl), 'self', MIN(record_id)
            FROM self_records
            GROUP BY hostname, ip_address, record_type
        ''')
        
        # other_records をコピー
        # 既に self_records として登録されているものと、other_records内の重複を排除
        cursor.execute('''
            INSERT INTO merged_records (hostname, ip_address, record_type, ttl, source_type, source_record_id)
            SELECT hostname, ip_address, record_type, MAX(ttl), 'other', MIN(record_id)
            FROM other_records
            WHERE NOT EXISTS (
                SELECT 1 FROM merged_records m 
                WHERE m.hostname = other_records.hostname 
                  AND m.ip_address = other_records.ip_address 
                  AND m.record_type = other_records.record_type
            )
            GROUP BY hostname, ip_address, record_type
        ''')
        
        conn.commit()

def _cleanup_records(db):
    # TODO: ttl 減算や古いレコード削除
    pass
