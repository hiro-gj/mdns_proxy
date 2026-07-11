try:
    import _thread as threading_fallback
    HAS_THREADING = False
except ImportError:
    threading_fallback = None

try:
    import threading
    HAS_THREADING = True
except ImportError:
    # MicroPython fallback
    pass

import socket
import select
try:
    import database
except ImportError:
    database = None

MDNS_ADDR = '224.0.0.251'
MDNS_PORT = 5353

def start_listener(db, sys_config=None):
    import sys
    if sys.platform == 'rp2' or not HAS_THREADING:
        if threading_fallback:
            threading_fallback.start_new_thread(_listen, (db, sys_config))
            # Pico環境向けに、LLMNR (ポート5355) スレッドも同時に起動させて Windows からの ping pc-0194 単体解決を両立させます
            threading_fallback.start_new_thread(listen_llmnr, (db, sys_config))
            return True
        else:
            # スレッドが使えない場合はメインスレッドでブロッキング実行する
            _listen(db, sys_config)
            return True
    else:
        t = threading.Thread(target=_listen, args=(db, sys_config), daemon=True)
        t.start()
        # 非Pico環境でもLLMNRを並行起動
        t2 = threading.Thread(target=listen_llmnr, args=(db, sys_config), daemon=True)
        t2.start()
        return t

def _setup_socket():
    from logger_config import logger
    import sys
    # UDPソケットの作成 (MicroPythonではsocket.IPPROTO_UDPが無い、または引数2つでもUDPになるためフォールバック)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    except AttributeError:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass
    
    # OS依存のオプション
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except AttributeError:
        pass
        
    # 自身のIPアドレスを取得
    my_ip = ''
    try:
        import network
        wlan = network.WLAN(network.STA_IF)
        if wlan.isconnected():
            my_ip = wlan.ifconfig()[0]
    except Exception:
        pass

    try:
        # Pico環境で既にOSが5353を掴んでいる場合は共有設定(SO_REUSEPORT相当)を利用してバインドを試みる
        if sys.platform == 'rp2':
            # SO_REUSEPORT (通常15だが環境による) を試す
            try:
                SO_REUSEPORT = getattr(socket, 'SO_REUSEPORT', 15)
                sock.setsockopt(socket.SOL_SOCKET, SO_REUSEPORT, 1)
            except Exception:
                pass
            
            # 【超重要】lwIPスタック制限の解消：
            # マルチキャストパケットを受信するため、ワイルドカードや個別IPではなく
            # マルチキャストアドレスそのもの（224.0.0.251）に直接 bind します
            try:
                sock.bind((MDNS_ADDR, MDNS_PORT))
                logger.info(f"[mDNS Server] Bound directly to multicast IP: {MDNS_ADDR}:{MDNS_PORT}")
            except OSError:
                try:
                    sock.bind(('', MDNS_PORT))
                    logger.info(f"[mDNS Server] Bound to wildcard: :{MDNS_PORT}")
                except OSError:
                    if my_ip:
                        sock.bind((my_ip, MDNS_PORT))
                        logger.info(f"[mDNS Server] Bound to device IP: {my_ip}:{MDNS_PORT}")
                    else:
                        sock.bind(('', MDNS_PORT))
        else:
            sock.bind(('', MDNS_PORT))
    except OSError as e:
        import time
        logger.warning(f"[mDNS Server] Port 5353 already in use ({e}). Trying to bind on temporary port and rely on Multicast JOIN...")
        try:
            sock.bind(('', 0)) # 空きポートでバインド
        except Exception as e2:
            logger.error(f"[mDNS Server] Temporary bind fail: {e2}")
            return None

    # マルチキャストグループに参加 (MicroPythonの定数不在エラーも考慮)
    try:
        IPPROTO_IP = getattr(socket, 'IPPROTO_IP', 0)
        IP_ADD_MEMBERSHIP = getattr(socket, 'IP_ADD_MEMBERSHIP', 1024)
        
        # lwIPスタック制限の解消：後半4バイト（インターフェースIP）に 0.0.0.0 ではなく、
        # 現在のアクティブな自身のWi-Fi IPを明示指定してJOINを確実に成功させます
        try:
            m_if_ip = my_ip if my_ip else '0.0.0.0'
            mreq = socket.inet_aton(MDNS_ADDR) + socket.inet_aton(m_if_ip)
            sock.setsockopt(IPPROTO_IP, IP_ADD_MEMBERSHIP, mreq)
        except Exception:
            if my_ip:
                ip_bytes = [int(p) for p in my_ip.split('.')]
            else:
                ip_bytes = [0, 0, 0, 0]
            mreq_bin = bytes([224, 0, 0, 251]) + bytes(ip_bytes)
            sock.setsockopt(IPPROTO_IP, IP_ADD_MEMBERSHIP, mreq_bin)
        logger.info(f"[mDNS Server] Joined multicast group {MDNS_ADDR} using interface {my_ip if my_ip else '0.0.0.0'}")
    except Exception as e:
        logger.error(f"[mDNS Server] Failed to join multicast group: {e}")
        return None

    # マルチキャスト送信設定: IP_MULTICAST_IF（送信IF明示）とTTL=255（②対応）
    # ※ Wi-Fi接続前に起動された場合は、IPが確定していないため送信IFの設定は遅延（またはスキップ）します。
    try:
        IPPROTO_IP = getattr(socket, 'IPPROTO_IP', 0)
        IP_MULTICAST_TTL = getattr(socket, 'IP_MULTICAST_TTL', 10)
        sock.setsockopt(IPPROTO_IP, IP_MULTICAST_TTL, 255)
        
        tmp_s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            tmp_s.connect(('8.8.8.8', 80))
            primary_ip = tmp_s.getsockname()[0]
            IP_MULTICAST_IF = getattr(socket, 'IP_MULTICAST_IF', 9)
            try:
                ip_aton = socket.inet_aton(primary_ip)
            except Exception:
                ip_aton = bytes([int(p) for p in primary_ip.split('.')])
            sock.setsockopt(IPPROTO_IP, IP_MULTICAST_IF, ip_aton)
            logger.info(f"[mDNS Server] Multicast send interface set to: {primary_ip}")
        except Exception:
            pass
        finally:
            tmp_s.close()
    except Exception as e:
        pass

    logger.info("[mDNS Server] Listening on UDP 5353...")
    return sock

def _listen(db, sys_config=None):
    from logger_config import logger
    sock = _setup_socket()
    if not sock:
        return

    while True:
        try:
            data, addr = sock.recvfrom(4096)
            _handle_query(db, sock, data, addr, sys_config)
        except Exception as e:
            logger.error(f"[mDNS Server] Error: {e}")

def setup_socket_llmnr():
    from logger_config import logger
    import sys
    # LLMNRポートは5355、マルチキャストIPは224.0.0.252
    LLMNR_PORT = 5355
    LLMNR_ADDR = "224.0.0.252"
    
    # 自身のIPアドレスを取得
    my_ip = ''
    try:
        import network
        wlan = network.WLAN(network.STA_IF)
        if wlan.isconnected():
            my_ip = wlan.ifconfig()[0]
    except Exception:
        pass

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            if sys.platform == 'rp2':
                # lwIPマルチキャスト受信制限の解消：
                # マルチキャストIPアドレスに直接 bind します
                sock.bind((LLMNR_ADDR, LLMNR_PORT))
                logger.info(f"[LLMNR Server] Bound directly to multicast IP: {LLMNR_ADDR}:{LLMNR_PORT}")
            else:
                sock.bind(('', LLMNR_PORT))
        except Exception as e:
            try:
                sock.bind(('', LLMNR_PORT))
            except Exception as e2:
                logger.error(f"[LLMNR Server] Could not bind to port 5355: {e2}")
                return None

        # マルチキャストグループに参加
        IPPROTO_IP = getattr(socket, 'IPPROTO_IP', 0)
        IP_ADD_MEMBERSHIP = getattr(socket, 'IP_ADD_MEMBERSHIP', 1024)
        try:
            m_if_ip = my_ip if my_ip else '0.0.0.0'
            mreq = socket.inet_aton(LLMNR_ADDR) + socket.inet_aton(m_if_ip)
            sock.setsockopt(IPPROTO_IP, IP_ADD_MEMBERSHIP, mreq)
        except Exception:
            if my_ip:
                ip_bytes = [int(p) for p in my_ip.split('.')]
            else:
                ip_bytes = [0, 0, 0, 0]
            mreq_bin = bytes([224, 0, 0, 252]) + bytes(ip_bytes)
            sock.setsockopt(IPPROTO_IP, IP_ADD_MEMBERSHIP, mreq_bin)
            
        logger.info(f"[LLMNR Server] Listening on UDP 5355 (Windows single-label resolution support) joined {LLMNR_ADDR}...")
        return sock
    except Exception as e:
        logger.error(f"[LLMNR Server] Init fail: {e}")
        return None

def handle_query_llmnr(db, sock, data, addr, sys_config=None):
    from logger_config import logger
    import struct
    try:
        if len(data) < 12:
            return
        
        tx_id, flags, qdcount, ancount, nscount, arcount = struct.unpack("!HHHHHH", data[:12])
        # クエリのみを処理
        if flags & 0x8000:
            return
            
        queried_hostname = _extract_hostname(data)
        if not queried_hostname:
            return
            
        # 単一ホスト解決 (.local やドメイン指定があれば除去)
        base_name = queried_hostname.split('.')[0]
        
        ip = None
        ttl = 30
        
        if db is not None:
            with db.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT ip_address, ttl FROM merged_records WHERE hostname = ? OR hostname = ?',
                    (base_name, f"{base_name}.local")
                )
                row = cursor.fetchone()
                if row:
                    ip, ttl = row
        
        if ip:
            ip_parts = ip.split('.')
            ip_bytes = bytes([int(p) for p in ip_parts])
            
            # LLMNR 応答ヘッダの構築
            resp_flags = 0x8000 # Response + No Error
            header = struct.pack("!HHHHHH", tx_id, resp_flags, 1, 1, 0, 0)
            
            # Question Sectionのコピー
            # ヘッダ直後の名前長さから質問セクションの終わりを特定
            name_len = data[12]
            q_end = 12 + 1 + name_len + 1 + 4 # Name + Null + Type(2) + Class(2)
            question = data[12:q_end]
            
            # Answer Section: Name (圧縮ポインタ 0xC00C), Type A(1), Class IN(1), TTL(4B), RDLENGTH(2B)=4, IP(4B)
            answer = struct.pack("!HHHLH4s", 0xC00C, 1, 1, ttl, 4, ip_bytes)
            
            sock.sendto(header + question + answer, addr)
            logger.info(f"[LLMNR Server] Replied {queried_hostname} -> {ip} to {addr}")
    except Exception as e:
        logger.error(f"[LLMNR Server] Error: {e}")

def listen_llmnr(db, sys_config=None):
    sock = setup_socket_llmnr()
    if not sock:
        return
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            handle_query_llmnr(db, sock, data, addr, sys_config)
        except Exception as e:
            from logger_config import logger
            logger.error(f"[LLMNR Server] Runtime Error: {e}")

def _get_my_ips():
    import sys
    # Pico環境の場合
    if sys.platform == 'rp2':
        try:
            import network
            wlan = network.WLAN(network.STA_IF)
            if wlan.isconnected():
                return [wlan.ifconfig()[0]]
        except Exception:
            pass
        return []
    ips = ['127.0.0.1', 'localhost']
    try:
        # ホスト名から解決
        ips.append(socket.gethostbyname(socket.gethostname()))
    except Exception:
        pass
    try:
        # ルーティングされるメインIPを取得
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))
            ips.append(s.getsockname()[0])
        finally:
            s.close()
    except Exception:
        pass
    return list(set(ips))

def _handle_query(db, sock, data, addr, sys_config=None):
    from logger_config import logger
    
    # QRビット確認: QR=1（応答パケット）は無視して早期リターン（自己ループ防止）
    if len(data) >= 3 and (data[2] & 0x80):
        return
    
    queried_hostname = _extract_hostname(data)
    if not queried_hostname:
        return

    # サービスタイプクエリ（アンダースコアで始まるサービス名）は名前解決プロキシの対象外として早期リターン
    if queried_hostname.startswith('_'):
        return

    # 自己解決（自己参照）ループ防止ガード
    # ipaddressモジュールはMicroPythonに存在しないため、文字列で簡易判定する
    is_loop = addr[0].startswith('127.') or addr[0] == '::1'

    my_ips = _get_my_ips()
    
    if sys_config and sys_config.has_section('network') and sys_config.has_option('network', 'mdns_hostname'):
        my_hostname = sys_config.get('network', 'mdns_hostname')
    else:
        try:
            my_hostname = socket.gethostname()
        except Exception:
            my_hostname = "mdns-proxy"
            
    is_query_for_me = (queried_hostname.lower() == my_hostname.lower() or 
                       queried_hostname.lower() == my_hostname.lower() + '.local')

    if (is_loop or addr[0] in my_ips) and is_query_for_me:
        return
        
    logger.info(f"[mDNS Server] Received query for: {queried_hostname} from {addr}")

    # 自身のホスト名のクエリかチェック
    if is_query_for_me:
        # 自身のIPアドレスを取得
        ip = None
        if my_ips:
            ip = my_ips[0]
        else:
            try:
                # 簡易的にUDPソケットを使って外部に接続するふりをして自身のIPを取得する
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    s.connect(('8.8.8.8', 80))
                    ip = s.getsockname()[0]
                finally:
                    s.close()
            except Exception as e:
                pass
        
        if ip:
            ttl = 120
            row = (ip, ttl)
        else:
            row = None
    else:
        if db is not None:
            with db.connection() as conn:
                cursor = conn.cursor()
                base_name = queried_hostname[:-6] if queried_hostname.endswith('.local') else queried_hostname
                local_name = base_name + '.local'
                cursor.execute(
                    'SELECT ip_address, ttl FROM merged_records WHERE hostname = ? OR hostname = ? OR hostname = ?',
                    (queried_hostname, base_name, local_name)
                )
                row = cursor.fetchone()
        else:
            row = None
        
    if row:
        ip, ttl = row
        # 応答パケットの構築
        response = _build_response(data, queried_hostname, ip, ttl, is_query_for_me)
        if response:
            from logger_config import logger
            # 受信用のソケット(5353ポートにバインド済み)を再利用して送信する
            # ※mDNSクライアントは送信元ポートが5353以外の応答を無視するため
            try:
                # クエリ送信元へユニキャスト
                sock.sendto(response, addr)
                # mDNSマルチキャストグループへも送信（ポート5353）
                # バインド済みのsockを再利用して送信元ポート5353を維持する
                try:
                    sock.sendto(response, (MDNS_ADDR, MDNS_PORT))
                except Exception as me:
                    logger.warning(f"[mDNS Server] Failed to send multicast: {me}")
            except Exception as e:
                logger.error(f"[mDNS Server] Failed to send response: {e}")
            logger.info(f"[mDNS Server] Replied to {addr} and multicast for {queried_hostname} -> {ip}")

def _extract_hostname(data):
    try:
        if len(data) < 12:
            return None
        # ヘッダー (12 bytes)
        # 質問数を取得
        qdcount = (data[4] << 8) | data[5]
        if qdcount == 0:
            return None
            
        offset = 12
        parts = []
        while True:
            if offset >= len(data):
                return None
            length = data[offset]
            if length == 0:
                offset += 1
                break
            if (length & 0xC0) == 0xC0:
                # ポインタ（ここでは簡易的に無視、通常クエリでは先頭に来るため）
                offset += 2
                break
            offset += 1
            parts.append(data[offset:offset+length].decode('utf-8'))
            offset += length
            
        if parts:
            return ".".join(parts)
    except Exception as e:
        pass
    return None

def _build_response(query_data, hostname, ip, ttl, is_unique=False):
    from logger_config import logger
    try:
        # TTL値が無効な時の安全な補完（デフォルト値を120とする）
        if ttl is None or not isinstance(ttl, int) or ttl < 0:
            ttl = 120

        # トランザクションIDをコピー
        tx_id = query_data[0:2]
        
        # Flags: 0x8400 (Authoritative Response)
        flags = (0x8400).to_bytes(2, 'big')
        
        # QDCOUNT=1, ANCOUNT=1, NSCOUNT=0, ARCOUNT=0（①対応: QDCOUNTを1に修正）
        counts = (1).to_bytes(2, 'big') + (1).to_bytes(2, 'big') + (0).to_bytes(2, 'big') + (0).to_bytes(2, 'big')
        
        header = tx_id + flags + counts
        
        # QNAME の構築（質問セクション用）
        name_parts = hostname.split('.')
        qname = bytes()
        for part in name_parts:
            qname += bytes([len(part)]) + part.encode('utf-8')
        qname += bytes([0])  # ルートラベル終端 (0x00)
        
        # 質問セクション: QNAME + QTYPE=A(1) + QCLASS=IN(1)（①対応: 質問セクションを追加）
        question_section = qname + (1).to_bytes(2, 'big') + (1).to_bytes(2, 'big')
        
        # アンサーセクション
        # NAME: ヘッダー(12バイト)直後のQNAMEへのDNS圧縮ポインタ (0xC00C)
        ans_name = bytes([0xC0, 0x0C])
        # Type A (1), Class IN (0x0001) または cache-flush付き (0x8001)
        # 自身のホスト名（ユニークレコード）の場合はcache-flushビットを立てる
        qclass = 0x8001 if is_unique else 0x0001
        type_class = (1).to_bytes(2, 'big') + (qclass).to_bytes(2, 'big')
        
        # TTL
        ttl_bytes = ttl.to_bytes(4, 'big')
        
        # RDLENGTH (4 bytes for IPv4)
        rdlength = (4).to_bytes(2, 'big')
        
        # RDATA (IP Address)
        ip_parts = ip.split('.')
        rdata = bytes([int(p) for p in ip_parts])
        
        answer_section = ans_name + type_class + ttl_bytes + rdlength + rdata
        
        response = header + question_section + answer_section
        return response
    except Exception as e:
        logger.error(f"[mDNS Server] Failed to build response for hostname={hostname}, ip={ip}, ttl={ttl}: {e}", exc_info=True)
        return None