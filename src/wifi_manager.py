import time

from .logger_config import logger

def connect(ssid, password):
    """
    Raspberry Pi Pico (MicroPython) での Wi-Fi 接続
    """
    try:
        import network
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        if not wlan.isconnected():
            logger.info(f"Connecting to network '{ssid}'...")
            wlan.connect(ssid, password)
            timeout = 10
            while not wlan.isconnected() and timeout > 0:
                time.sleep(1)
                timeout -= 1
        
        if wlan.isconnected():
            logger.info(f"Network connected: {wlan.ifconfig()}")
        else:
            logger.error("Failed to connect to network")
    except ImportError:
        logger.warning("network module not found. This feature is only for MicroPython.")
    except Exception as e:
        logger.error(f"Wi-Fi connection error: {e}")
