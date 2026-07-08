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

※ コマンドラインから `sed` を使用して置換する場合は、以下のコマンドを実行します。
```bash
sed -i 's/#define LWIP_DNS_SUPPORT_MDNS_QUERIES   1/#define LWIP_DNS_SUPPORT_MDNS_QUERIES   0/' extmod/lwip-include/lwipopts_common.h
sed -i 's/#define LWIP_MDNS_RESPONDER             1/#define LWIP_MDNS_RESPONDER             0/' extmod/lwip-include/lwipopts_common.h
```

## 5. Pico W 向けビルド

```bash
cd ports/rp2

make submodules

make -j$(nproc) BOARD=RPI_PICO_W
```

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

```python
import socket

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("0.0.0.0", 5353))

print("OK")
```

OK と表示されれば UDP 5353 を Python から利用可能です。

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
