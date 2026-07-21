#
#    Copyright 2024-2026 Jeroen van Oosterhout <18647330+jvanoosterhout@users.noreply.github.com>
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
#    Pin keeper class to create and manage all pins

from DGB.PinOut import Pin_out
from DGB.PinIn import Pin_in
from DGB.PinCount import Pin_count
from DGB.PinNWayOut import Pin_N_way_out
from DGB.Pin import Pin
from DGB.PinModels import PinType, PinModel
from DGB.DGBContext import DGBContext, DuplicatePolicy
import logging


class PinKeeper(object):
    def __init__(
        self,
        dgb_context: DGBContext,
        pin_pw_list: dict = {},
    ):
        """
        Initialize the PinKeeper class with default values.
        """
        self.PinPWList = pin_pw_list
        self.PinList: list[Pin] = []
        self.logger = logging.getLogger("PinKeeper")
        self.dgb_context = dgb_context
        logging.getLogger().setLevel(logging.INFO)

        self.logger.info("PinKeeper initialized.")

    def __del__(self):
        for pin in self.PinList:
            pin.pin_device.close()
        self.logger.info("PinKeeper cleaned up all pins")

    def GetPin(self, config: PinModel):
        """
        Get pin value, if it exists, otherewise try to make it.

        Parameters:
        config (Pin): Configuration of the pin.

        Returns:
        float/bool/None: Value of the pin or False or None.
        """
        pin_id = self.DoIExist(config)
        if isinstance(pin_id, bool):  # is pin config, but does not exist jet
            self.logger.info(
                "Is config for pin{}, but does not exist jet.".format(config.pin)
            )
            if self.SetPin(config):
                pin_id = self.DoIExist(config)
                return self.PinList[pin_id].GetPinValue()
        else:  # is pin config, and it exists --> ask its value
            self.logger.info(
                "Is config for pin {}, and it exists, therefore requesting its value.".format(
                    config.pin
                )
            )
            return self.PinList[pin_id].GetPinValue()

        self.logger.info("Got an unrecognized configuration.")
        return False

    def SetPin(
        self, config: PinModel, policy: DuplicatePolicy = DuplicatePolicy.SKIP
    ) -> bool:
        """
        Set the configuration of a pin, in case the pin does not jet exists, it sends to creates one.

        Parameters:
        config (Pin): Configuratie van de pin.

        Returns:
        bool: True if succesfully made or new settings succesfully processed, otherwise False.
        """
        if not self._handle_existing_pin(config.pin, policy):
            return False

        pin_id = self.DoIExist(config)
        if isinstance(pin_id, bool):  # pin does not exist jet
            if config.ptype == PinType.pinnwayout.value:
                # check if n ways do also not jet exist
                for p in config.pin_list:
                    if p >= 0 and not p == config.pin:
                        if isinstance(
                            self.DoIExist(
                                PinModel({"pin": p, "ptype": PinType.pinout.value}), int
                            )
                        ):
                            self.logger.warning(
                                "Pin {} already exists. Cannot override existing pin to make an nwayout pin.".format(
                                    p
                                )
                            )
                            return False
            if self.MakeNewPin(config):
                return True
            else:
                self.logger.warning("No pin configuration recognized.")
                return False
        else:  # is pin config, and exists, thus process update
            self.logger.info("Proces update for pin {}.".format(config.pin))
            if self.PinList[pin_id].config.pin in self.PinPWList:
                if not self.PinList[pin_id].CheckPW(config.password):
                    self.logger.warning("Worng password for pin {}!".format(config.pin))
                    return False
            if self.PinList[pin_id].HasSameConfig(config):
                return self.PinList[pin_id].ProcessPinUpdate(config)
            else:
                return False

    def _handle_existing_pin(
        self,
        pin: int,
        policy: DuplicatePolicy,
    ) -> bool:
        """
        Check whether a pin already exists and apply policy.

        Returns:
            True  -> caller may proceed with creating/updating the pin
            False -> caller must skip
        """
        existing = next((p for p in self.PinList if p.config.pin == pin), None)
        if existing is None:  # pin does not exist yet
            return True

        if policy == DuplicatePolicy.SKIP:
            self.logger.warning(f"Pin {pin} already exists -- skipping")
            return False

        self.logger.warning(
            f"Pin {pin} already exists -- unknown policy '{policy}', skipping"
        )
        return False

    def DoIExist(self, config: PinModel):
        """
        Check if a pin allready exists in PinList.

        Parameters:
        config (Pin): Configuration of the pin.

        Returns:
        int/bool: Index of the pin in the PinList or False.
        """

        if self.PinList == []:
            return False
        for pin in self.PinList:
            if pin.config.pin == config.pin:
                return self.PinList.index(pin)
        return False

    def MakeNewPin(self, config: PinModel) -> bool:
        """
        Create a new pin based on the configuration optained from the rest call

        Parameters:
        config (Pin): Configuration of the pin.

        Returns:
        bool: True if succesfully made, otherwise False.
        """
        self.logger.info("Make a new pin with config: {}".format(config))
        pw_needed = False
        if config.pin in self.PinPWList:
            if config.password is not None:
                if config.password == self.PinPWList[config.pin]:
                    pw_needed = True
                else:
                    self.logger.warning("Worng password for pin {}!".format(config.pin))
                    return False
            else:
                self.logger.warning(
                    "No password provided for pin {}, while this is required!".format(
                        config.pin
                    )
                )
                return False
        if config.ptype is PinType.pinout.value:
            P = Pin_out(config=config, dgb_context=self.dgb_context)
            self.dgb_context.add_object(
                str(config.pin), P, {"on": P.on, "off": P.off, "blink": P.blink}
            )
        elif config.ptype is PinType.pinin.value:
            P = Pin_in(config=config, dgb_context=self.dgb_context)
            self.dgb_context.add_object(str(config.pin), P)
        elif config.ptype is PinType.pincount.value:
            P = Pin_count(config=config, dgb_context=self.dgb_context)
            self.dgb_context.add_object(str(config.pin), P)
        elif config.ptype is PinType.pinnwayout.value:
            P = Pin_N_way_out(config=config, dgb_context=self.dgb_context)
            self.dgb_context.add_object(
                str(config.pin), P, {"on": P.on, "off": P.off, "blink": P.blink}
            )
            for lst in range(len(config.pin_list)):
                if not config.pin_list[lst] == config.pin and config.pin_list[lst] >= 0:
                    sub_config = P.GenerateSubPinConfig(lst)
                    self.logger.info("Configure sub pin {}.".format(sub_config))
                    N = Pin_out(
                        config=sub_config,
                        is_PinNWayOut=True,
                        dgb_context=self.dgb_context,
                    )
                    N.ConfigurePin()
                    P.Pins.append(N)
                    self.PinList.append(N)
                    self.dgb_context.add_object(str(sub_config.pin), N)
        else:
            return False
        if pw_needed:
            P.pw = {config.pin: self.PinPWList[config.pin]}
        self.logger.info("Configure pin {}.".format(P.config.pin))
        P.ConfigurePin()
        if not P.ProcessPinUpdate(config):
            self.logger.error("Could not set pin update")
        self.logger.info("Add pin {} to PinList".format(P.config.pin))
        self.PinList.append(P)
        self.logger.info(self.dgb_context.get_object(str(P.config.pin)).config)
        self.logger.info("Pin {} added to PinList.".format(P.config.pin))
        return True
