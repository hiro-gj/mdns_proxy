import os
import sys
import time

def get_platform():
    try:
        import machine
        return 'pico'
    except ImportError:
        return 'windows' if os.name == 'nt' else 'linux'

# ログディレクトリとDBディレクトリの作成
if get_platform() != 'pico':
    for dir_name in ['log', 'db']:
        os.makedirs(os.path.join(os.path.dirname(os.path.dirname(__file__)), dir_name), exist_ok=True)

from . import config
from . import database
from . import scheduler
from . import mdns_server
from . import api_server
from . import cli
from .logger_config import logger

def main():
    logger.info("mDNS Proxy Starting...")
    
    # 1. 設定読み込み
    sys_config = config.load_system_config()
    hosts_config = config.load_hosts_config()

    # Picoの場合はWi-Fi接続
    if get_platform() == 'pico':
        from . import wifi_manager
        wifi_manager.connect(sys_config.get('network', 'wifi_ssid'), sys_config.get('network', 'wifi_password'))

    # 2. データベース初期化
    db = database.Database()
    db.init_db()
    db.sync_static_hosts(hosts_config)

    # 3. 各サーバーやプロセスの起動
    # APIサーバー(HTTP)をバックグラウンドまたはスレッド等で起動
    port = int(sys_config.get('system', 'port', fallback='80'))
    api_server.start_server(db, port=port)
    
    # mDNSサーバーのリスナー起動
    mdns_server.start_listener(db)

    # 4. スケジューラの開始（ループ）
    scheduler.start(db, sys_config)

    # 5. CLI（対話モード）※非デーモン時
    try:
        cli.run(db, sys_config)
    except KeyboardInterrupt:
        logger.info("Shutting down...")

if __name__ == '__main__':
    main()
