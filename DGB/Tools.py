#
#    Copyright 2026 Jeroen van Oosterhout <18647330+jvanoosterhout@users.noreply.github.com>
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
#
#

import logging

logger = logging.getLogger("Tools")
logging.basicConfig(level="INFO")


class IOT_tools:
    def is_float(self: str) -> bool:
        try:
            float(self)
            logger.debug(f"{self} is een geldige float.")
            return True
        except ValueError:
            logger.debug(f"{self} is geen geldige float.")
            return False

    def is_int(self: str) -> bool:
        try:
            int(self)
            logger.debug(f"{self} is een geldige integer.")
            return True
        except ValueError:
            logger.debug(f"{self} is geen geldige integer.")
            return False

    def strtobool(self: str) -> int:
        """Convert a string representation of truth to true (1) or false (0).
        True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
        are 'n', 'no', 'f', 'false', 'off', and '0'.  Raises ValueError if
        'val' is anything else.
        """
        value = self.lower()
        if value in ("y", "yes", "t", "true", "on", "1"):
            return 1
        elif value in ("n", "no", "f", "false", "off", "0"):
            return 0
        else:
            raise ValueError(f"invalid truth value {value!r}")
