import logging

logger = logging.getLogger("Tools")
logging.basicConfig(level='INFO')

class IOT_tools():

    def is_float(str:str) -> bool:
        try:
            num = float(str)
            logger.debug(f"{str} is een geldige float.")
            return True
        except ValueError:
            logger.debug(f"{str} is geen geldige float.")
            return False
        
    def is_int(str:str) -> bool:
        try:
            num = int(str)
            logger.debug(f"{str} is een geldige integer.")
            return True
        except ValueError:
            logger.debug(f"{str} is geen geldige integer.")
            return False
        
    def strtobool (val:str) -> int:
        """Convert a string representation of truth to true (1) or false (0).
        True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
        are 'n', 'no', 'f', 'false', 'off', and '0'.  Raises ValueError if
        'val' is anything else.
        """
        val = val.lower()
        if val in ('y', 'yes', 't', 'true', 'on', '1'):
            return 1
        elif val in ('n', 'no', 'f', 'false', 'off', '0'):
            return 0
        else:
            raise ValueError("invalid truth value %r" % (val,))