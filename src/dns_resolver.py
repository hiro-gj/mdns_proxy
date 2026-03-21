import socket
import os
import subprocess

def resolve_all(db, sys_config):
    """static_hosts に登録されているホストを全て名前解決し、self_records に登録する"""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT host_id, hostname FROM static_hosts')
        hosts = cursor.fetchall()

        for host_id, hostname in hosts:
            ip, method = _resolve_host(hostname)
            if ip:
                ttl = int(sys_config.get('system', 'ttl', fallback='120'))
                # 既存レコードがあれば更新、なければ追加
                cursor.execute('SELECT record_id FROM self_records WHERE hostname = ?', (hostname,))
                if cursor.fetchone():
                    cursor.execute('''
                        UPDATE self_records 
                        SET ip_address = ?, resolution_method = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE hostname = ?
                    ''', (ip, method, hostname))
                else:
                    cursor.execute('''
                        INSERT INTO self_records (hostname, ip_address, record_type, ttl, resolution_method)
                        VALUES (?, ?, 'A', ?, ?)
                    ''', (hostname, ip, ttl, method))
        
        conn.commit()

def _resolve_host(hostname):
    """
    複数手法で名前解決を試みる。
    簡易的に socket.gethostbyname 等を使用。
    """
    ip = None
    method = None

    try:
        ip = socket.gethostbyname(hostname)
        method = 'socket'
    except Exception as e:
        # PING 等へのフォールバック（ここでは簡易的に省略）
        pass

    return ip, method
