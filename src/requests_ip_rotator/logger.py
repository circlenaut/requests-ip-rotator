import logging
import pathlib
import traceback

__all__ = ['Logger']


class Logger:

    def __init__(self, name=None, level=None):
        
        self.name = name
        self.level = level if level else "INFO"

        self.log = self.setup(self.name)
        self.set_level(self.level)

    def setup(self, name: str) -> logging.Logger:
        datefmt = '%Y-%m-%d %H:%M:%S %z'
        formatter='[%(asctime)s] [%(process)d] [%(levelname)s] %(message)s'
        
        logging.basicConfig(format = formatter, datefmt=datefmt)
        return logging.getLogger(name)

    def set_level(self, level):
        if level:
            if level.upper() in ['FATAL', 'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']:
                self.log.setLevel(level.upper())
            else:
                self.log.error(f"Invalid logging level: '{level}'")
        else:
            self.log.error(f"Log level is undefined for logger: '{self.name}'")

    def get_level(self, name=None):
        if name:
            return logging.getLevelName(name)
        else:
            return logging.getLevelName(self.log.getEffectiveLevel())

    def save(self, path, level='DEBUG'):
        if path:
            path_dir = pathlib.Path(path).parent
            if  pathlib.Path.exists(path_dir):
                formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
                fh = logging.FileHandler(path)
                fh.setLevel(level.upper())
                fh.setFormatter(formatter)
                self.log.addHandler(fh)   
            else:
                self.log.error(f"Invalid logging directory: '{path_dir}'")
        else:
            self.log.warning(f"Log save path is undefined")

    def fatal(self, msg):
        self.log.fatal(msg)

    def critical(self, msg):
        self.log.critical(msg)

    def error(self, msg):
        self.log.error(msg)

    def warning(self, msg):
        self.log.warning(msg)
   
    def info(self, msg):
        self.log.info(msg)

    def debug(self, msg):
        self.log.debug(msg)