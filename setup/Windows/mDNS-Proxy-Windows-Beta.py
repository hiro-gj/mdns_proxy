import socket
import struct
import time
import urllib.request
import json
import select
import os

MDNS_ADDR = "224.0.0.251"
MDNS_PORT = 5353
TYPE_A = 1
TYPE_ANY = 255
CLASS_IN = 1
CLASS_FLUSH_IN = 0x8001

def load_system_ini_proxy_url():
    # system.ini から external_proxies を動的抽出する
    # このスクリプトの位置 (setup/Windows/mDNS-Proxy-Windows-Beta.py) からプロジェクトルートの system.ini を探す
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ini_path = os.path.join(base_dir, 'system.ini')
    
    if not os.path.exists(ini_path):
        # カレントディレクトリや、同一フォルダ、親フォルダを探すフォールバック
        ini_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'system.ini')
        if not os.path.exists(ini_path):
            ini_path = 'system.ini'
            
    proxy_url = None # セキュリティのため会社固有情報はハードコードせず、Noneで初期化します
    
    if os.path.exists(ini_path):
        try:
            with open(ini_path, 'r', encoding='utf-8') as f:
                current_section = None
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or line.startswith(';'):
                        if line.startswith('[') and line.endswith(']'):
                            current_section = line[1:-1]
                        continue
                    if line.startswith('[') and line.endswith(']'):
                        current_section = line[1:-1]
                    elif '=' in line and current_section == 'network':
                        key, val = line.split('=', 1)
                        if key.strip() == 'external_proxies':
                            proxies_str = val.strip()
                            if proxies_str:
                                # カンマ区切りの最初のプロキシを使用する（PicoW実機のホスト名やIPが記述されていることを想定）
                                # ※ 動的にPicoのホスト名「pico-host.local:80」などをパースします
                                first_proxy = proxies_str.split(',')[0].strip()
                                # もし最初のプロキシが自分自身等で都合が悪い場合は、もう一方を取得
                                if ('localhost' in first_proxy or '127.0.0.1' in first_proxy) and len(proxies_str.split(',')) > 1:
                                    first_proxy = proxies_str.split(',')[1].strip()
                                    
                                if first_proxy:
                                    if ':' in first_proxy:
                                        ip, port = first_proxy.split(':', 1)
                                    else:
                                        ip, port = first_proxy, "53080"
                                    proxy_url = f"http://{ip}:{port}/api/merged-records"
                                    break
        except Exception as e:
            print("Failed to read system.ini for external_proxies:", e)
    return proxy_url

def load_records_from_proxy():
    try:
        url = load_system_ini_proxy_url()
        if not url:
            print("No dynamic proxy URL found in system.ini. Skipping sync.")
            return {}
        print(f"Syncing from dynamic URL: {url}")
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=3) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                records = {}
                for r in data:
                    hostname = r['hostname']
                    if not hostname.endswith('.local'):
                        hostname = f"{hostname}.local"
                    records[hostname.lower().encode('ascii')] = r['ip_address']
                return records
    except Exception as e:
        print("Failed to sync records from external proxy:", e)
    return {}

def decode_name(packet, offset):
    labels = []
    jumped = False
    original_offset = offset
    jumps = 0

    while True:
        if offset >= len(packet):
            raise ValueError("bad dns name")
        length = packet[offset]
        if (length & 0xC0) == 0xC0:
            if offset + 1 >= len(packet):
                raise ValueError("bad compression pointer")
            ptr = ((length & 0x3F) << 8) | packet[offset + 1]
            if not jumped:
                original_offset = offset + 2
            offset = ptr
            jumped = True
            jumps += 1
            if jumps > 8:
                raise ValueError("too many compression jumps")
            continue
        if length == 0:
            offset += 1
            break
        offset += 1
        labels.append(packet[offset:offset + length])
        offset += length

    name = b".".join(labels).lower()
    if jumped:
        return name, original_offset
    return name, offset

def encode_name(name):
    out = bytearray()
    for label in name.split(b"."):
        out.append(len(label))
        out.extend(label)
    out.append(0)
    return bytes(out)

def build_a_response(qname, ip):
    tid = 0
    flags = 0x8400  # response + authoritative answer
    qname_wire = encode_name(qname)
    question = qname_wire + struct.pack("!HH", TYPE_A, CLASS_IN)
    answer = (
        b"\xC0\x0C" +
        struct.pack("!HHIH", TYPE_A, CLASS_FLUSH_IN, 120, 4) +
        socket.inet_aton(ip)
    )
    header = struct.pack("!HHHHHH", tid, flags, 1, 1, 0, 0)
    return header + question + answer

def open_socket():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass
    s.bind(("", MDNS_PORT))
    group = socket.inet_aton(MDNS_ADDR)
    iface = socket.inet_aton("0.0.0.0")
    mreq = group + iface
    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    try:
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
    except OSError:
        pass
    return s

def main():
    records = load_records_from_proxy()
    last_sync_time = time.time()
    s = open_socket()

    print("Windows mDNS Proxy Beta Daemon listening on UDP 5353...")
    print("Initial Synced records:", records)

    while True:
        r, _, _ = select.select([s], [], [], 1.0)
        
        # 30秒ごとに外部・Pico実機プロキシから再同期
        if time.time() - last_sync_time > 30:
            new_records = load_records_from_proxy()
            if new_records:
                records = new_records
                print("Re-synced records:", records)
            last_sync_time = time.time()

        if not r:
            continue

        packet, addr = s.recvfrom(1500)
        if len(packet) < 12:
            continue

        try:
            tid, flags, qdcount, ancount, nscount, arcount = struct.unpack("!HHHHHH", packet[:12])
        except Exception:
            continue

        # クエリのみを処理 (QR=0)
        if flags & 0x8000:
            continue

        offset = 12
        for _ in range(qdcount):
            try:
                qname, offset2 = decode_name(packet, offset)
                if offset2 + 4 > len(packet):
                    break
                qtype, qclass = struct.unpack("!HH", packet[offset2:offset2 + 4])
                offset = offset2 + 4
            except Exception:
                break

            if qname in records and (qtype == TYPE_A or qtype == TYPE_ANY):
                ip = records[qname]
                resp = build_a_response(qname, ip)
                qu = bool(qclass & 0x8000)
                dest = addr if qu else (MDNS_ADDR, MDNS_PORT)
                s.sendto(resp, dest)
                print(f"Replied: {qname.decode()} -> {ip} to {dest}")

if __name__ == "__main__":
    main()
