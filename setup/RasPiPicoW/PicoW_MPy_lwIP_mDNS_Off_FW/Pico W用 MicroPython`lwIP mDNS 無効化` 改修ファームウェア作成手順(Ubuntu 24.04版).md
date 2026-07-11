# Pico W用 MicroPython`lwIP mDNS 無効化` 改修ファームウェア作成手順(Ubuntu 24.04版)

## 目的
Pico W の標準 MicroPython ファームウェアで有効になっている lwIP mDNS を無効化し、Python側で独自 mDNS サーバーを実装できるようにする。

---

## 修正点（元手順からの変更点）
- `BOARD=PICO_W` の指定は、現在の MicroPython リポジトリ（rp2 ポートの Makefile）において **`BOARD=RPI_PICO_W`** に変更されています。旧指定のままだと `Invalid BOARD specified` エラーが発生します。
- `lwIP mDNS` 無効化の対象ファイルは `extmod/lwip-include/lwipopts_common.h` です。

---

## 1. 必要パッケージのインストール

```bash
sudo apt update

sudo apt install -y git build-essential cmake gcc-arm-none-eabi python3 python3-pip
```

確認:

```bash
arm-none-eabi-gcc --version
cmake --version
python3 --version
```

## 2. MicroPython ソース取得

```bash
mkdir -p ~/src
cd ~/src

git clone https://github.com/micropython/micropython.git
cd micropython

git submodule update --init --recursive
```

## 3. mpy-cross ビルド

```bash
make -C mpy-cross -j$(nproc)
```

## 4. mDNS 設定編集（lwIP mDNS 無効化）

`extmod/lwip-include/lwipopts_common.h` を編集し、以下のように設定値を `1` から `0` に変更します。

**変更前 (59〜60行目付近):**
```c
#define LWIP_DNS_SUPPORT_MDNS_QUERIES   1
#define LWIP_MDNS_RESPONDER             1
```

**変更後:**
```c
#define LWIP_DNS_SUPPORT_MDNS_QUERIES   0
#define LWIP_MDNS_RESPONDER             0
```

※ コマンドラインから `sed` を使用して置換する場合は、以下のコマンドを実行します（スペースのゆらぎにも対応）。
```bash
sed -i -E 's/#define[[:space:]]+LWIP_DNS_SUPPORT_MDNS_QUERIES[[:space:]]+1/#define LWIP_DNS_SUPPORT_MDNS_QUERIES   0/' extmod/lwip-include/lwipopts_common.h
sed -i -E 's/#define[[:space:]]+LWIP_MDNS_RESPONDER[[:space:]]+1/#define LWIP_MDNS_RESPONDER             0/' extmod/lwip-include/lwipopts_common.h
```
> **手動編集の場合:** `extmod/lwip-include/lwipopts_common.h` の 59〜60行目付近をテキストエディタで開き、値を `1` から `0` に変更してください。

## 5. Pico W 向けビルド

```bash
cd ports/rp2

make submodules

make -j$(nproc) BOARD=RPI_PICO_W
```
> **補足:** 上記コマンドは `micropython/ports/rp2` ディレクトリ内で実行してください。プロジェクトルート（`micropython/`）から `make` を実行しても `BOARD=RPI_PICO_W` は認識されません。

## 6. 成果物

```text
ports/rp2/build-RPI_PICO_W/firmware.uf2
```

## 7. Pico Wへ書込み

1. BOOTSEL を押しながら USB 接続
2. RPI-RP2 ドライブが現れる
3. firmware.uf2 をコピー

```bash
cp build-RPI_PICO_W/firmware.uf2 /media/$USER/RPI-RP2/
```

## 8. 動作確認

lwIP mDNS が無効化され、Python 側が UDP 5353 を自由に使えることを検証します。

### 検証スクリプト（Pico W の REPL で実行）

```python
import socket
import select
import struct
import time

# 1) バインド確認
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    sock.bind(("0.0.0.0", 5353))
    print("[OK] bind 0.0.0.0:5353 succeeded")
except Exception as e:
    print("[NG] bind failed:", e)
    raise SystemExit

# 2) マルチキャストグループ参加確認
try:
    mreq = bytes([224, 0, 0, 251]) + bytes([0, 0, 0, 0])
    sock.setsockopt(0, 1024, mreq)  # IPPROTO_IP=0, IP_ADD_MEMBERSHIP=1024
    print("[OK] multicast join succeeded")
except Exception as e:
    print("[WARN] multicast join:", e)

# 3) 自己応答の送受信テスト（実際の mDNS パケット送受信を検証）
# 簡易な mDNS クエリを自分自身に送信し、同じソケットで受信できるか確認
tx_id = 0x1234
header = struct.pack("!HHHHHH", tx_id, 0x0000, 1, 0, 0, 0)
qname = b"\x04test\x05local\x00"
qtype_qclass = struct.pack("!HH", 1, 1)
query = header + qname + qtype_qclass

try:
    # 送信元ポート 5353 で送信できるか（他の mDNS デーモンがいない場合のみ成功）
    sock.sendto(query, ("224.0.0.251", 5353))
    print("[OK] sendto on 5353 succeeded")
except Exception as e:
    print("[WARN] sendto:", e)

# 短時間待機して受信確認
time.sleep(0.5)
ready, _, _ = select.select([sock], [], [], 1.0)
if ready:
    data, addr = sock.recvfrom(1024)
    print("[OK] recvfrom succeeded (bytes=", len(data), "from=", addr, ")")
else:
    print("[INFO] no response received (expected if no other mDNS responder is running)")

print("\nAll checks completed. UDP 5353 is available for Python mDNS implementation.")
```

上記スクリプトを実行し、`[OK]` が複数表示されれば、lwIP mDNS の無効化と Python 側でのポート利用が正常に機能しています。

## トラブルシュート

### submodule関連エラー

```bash
git submodule update --init --recursive
```

### メモリ不足

```bash
make BOARD=RPI_PICO_W
```

### USBドライブが見えない

```bash
lsblk
```

で RPI-RP2 が認識されているか確認します。
