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

def _sync_to_others(db, sys_config):
    # TODO: self_records の内容を HTTP(POST) で other_proxies に送信する
    pass

def _merge_records(db):
    with db.get_connection() as conn:
        cursor = conn.cursor()
        # 一旦全クリア
        cursor.execute('DELETE FROM merged_records')
        
        # self_records をコピー
        cursor.execute('''
            INSERT INTO merged_records (hostname, ip_address, record_type, ttl, source_type, source_record_id)
            SELECT hostname, ip_address, record_type, ttl, 'self', record_id
            FROM self_records
        ''')
        
        # other_records をコピー
        cursor.execute('''
            INSERT INTO merged_records (hostname, ip_address, record_type, ttl, source_type, source_record_id)
            SELECT hostname, ip_address, record_type, ttl, 'other', record_id
            FROM other_records
        ''')
        
        conn.commit()

def _cleanup_records(db):
    # TODO: ttl 減算や古いレコード削除
    pass
