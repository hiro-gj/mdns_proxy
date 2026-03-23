import logging
import logging.handlers
import os
import zipfile
import glob
from datetime import datetime

class ZipRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    def __init__(self, filename, when='D', interval=1, backupCount=3, encoding=None, delay=False, utc=False, atTime=None):
        super().__init__(filename, when, interval, backupCount, encoding, delay, utc, atTime)

    def doRollover(self):
        super().doRollover()
        self._zip_old_logs()

    def _zip_old_logs(self):
        dir_name, base_name = os.path.split(self.baseFilename)
        log_pattern = os.path.join(dir_name, base_name + ".*")
        log_files = glob.glob(log_pattern)

        for log_file in log_files:
            if not log_file.endswith('.zip') and os.path.isfile(log_file):
                zip_filename = log_file + '.zip'
                try:
                    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zf:
                        zf.write(log_file, os.path.basename(log_file))
                    os.remove(log_file)
                except Exception as e:
                    print(f"Failed to zip log file {log_file}: {e}")

        # Ensure we keep only backupCount of zip files
        zip_pattern = os.path.join(dir_name, base_name + ".*.zip")
        zip_files = glob.glob(zip_pattern)
        zip_files.sort(key=os.path.getmtime)
        while len(zip_files) > self.backupCount:
            file_to_remove = zip_files.pop(0)
            try:
                os.remove(file_to_remove)
            except OSError:
                pass

def setup_logger():
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'log')
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, 'mdns_proxy.log')
    
    logger = logging.getLogger('mdns_proxy')
    logger.setLevel(logging.DEBUG)
    
    # Avoid adding multiple handlers if setup_logger is called multiple times
    if not logger.handlers:
        # File handler (daily rotation, keep 3 backups as zip)
        file_handler = ZipRotatingFileHandler(
            filename=log_file,
            when='midnight',
            interval=1,
            backupCount=3,
            encoding='utf-8'
        )
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
        
        logger._console_handler = console_handler
        
    return logger

logger = setup_logger()

def disable_console_logging():
    if hasattr(logger, '_console_handler') and logger._console_handler in logger.handlers:
        logger.removeHandler(logger._console_handler)

def enable_console_logging():
    if hasattr(logger, '_console_handler') and logger._console_handler not in logger.handlers:
        logger.addHandler(logger._console_handler)
