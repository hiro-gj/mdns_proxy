import threading
import socket
import select
from . import database

MDNS_ADDR = '224.0.0.251'
MDNS_PORT = 5353

def start_listener(db):
    t = threading.Thread(target=_listen, args=(db,), daemon=True)
    t.start()
    return t

def _listen(db):
    # UDPソケットの作成
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # OS依存のオプション
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except AttributeError:
        pass
        
    sock.bind(('', MDNS_PORT))
    
    from .logger_config import logger

    # マルチキャストグループに参加
    try:
        mreq = socket.inet_aton(MDNS_ADDR) + socket.inet_aton('0.0.0.0')
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    except Exception as e:
        logger.error(f"[mDNS Server] Failed to join multicast group: {e}")
        return

    logger.info("[mDNS Server] Listening on UDP 5353...")
    
    while True:
        try:
            data, addr = sock.recvfrom(4096)
            # 簡易的に、クエリ受信時に常にDBを検索し、一致があれば応答を返す
            # 実際にはDNSパケットのパースと、それに合わせた応答パケットの構築が必要。
            _handle_query(db, sock, data, addr)
        except Exception as e:
            logger.error(f"[mDNS Server] Error: {e}")

def _handle_query(db, sock, data, addr):
    # DNSパケットのパース処理（簡易実装としてダミー）
    # クエリされたホスト名を取得
    queried_hostname = _extract_hostname(data)
    if not queried_hostname:
        return
        
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT ip_address, ttl FROM merged_records WHERE hostname = ?',
            (queried_hostname,)
        )
        row = cursor.fetchone()
        
    if row:
        ip, ttl = row
        # 応答パケットの構築
        response = _build_response(data, queried_hostname, ip, ttl)
        if response:
            from .logger_config import logger
            sock.sendto(response, (MDNS_ADDR, MDNS_PORT))
            logger.debug(f"[mDNS Server] Replied to {addr} for {queried_hostname} -> {ip}")

def _extract_hostname(data):
    # 実際のパースロジックは煩雑なため省略
    # 簡易的に、パケット内に含まれるホスト名らしい文字列を抽出
    # (ここではダミーとして None を返す)
    return None

def _build_response(query_data, hostname, ip, ttl):
    # mDNS応答パケットの構築 (ダミー実装)
    return None
