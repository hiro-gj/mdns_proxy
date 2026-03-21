import os
import configparser

def get_base_dir():
    # src/ の親ディレクトリ（mdns_proxy/）を基準にする
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_system_config():
    config = configparser.ConfigParser()
    path = os.path.join(get_base_dir(), 'system.ini')
    if os.path.exists(path):
        config.read(path, encoding='utf-8')
    else:
        # デフォルト設定
        config.add_section('system')
        config.set('system', 'interval', '30')
        config.set('system', 'token_prefix', 'mDNSProxy_')
        config.set('system', 'port', '80')
        config.set('system', 'ttl', '120')
        config.add_section('network')
        config.set('network', 'external_proxies', '')
        config.set('network', 'wifi_ssid', '')
        config.set('network', 'wifi_password', '')
    return config

def load_hosts_config():
    config = configparser.ConfigParser(allow_no_value=True)
    path = os.path.join(get_base_dir(), 'search_hosts.ini')
    if os.path.exists(path):
        config.read(path, encoding='utf-8')
    else:
        config.add_section('hosts')
    return config
