#!/usr/bin/env python
# encoding: utf-8
"""
Generieke pin configurator class

Jeroen van Oosterhout, 15-07-2024
"""
from PinAPI.Pin import *

class Pin_count(Pin):
    def __init__(self, HASS_interface: Client, pin, ptype):
        if not ptype == "count":
            self.logger.error('Verkeerde type. Kreeg "{}", verwachte "out"'.format(ptype))
            return False
        super().__init__(pin=pin, HASS_interface=HASS_interface, ptype=ptype)
        self.count_totaal = 0
        self.tijd_laatste_count = time.monotonic()
        self.count_laatste_blok = 0 
        self.tijd_laatste_block = time.monotonic()
        self.stroom = 0 # pulsen per minut

        self.calibrationFactor = 1 #6.6


    def HasSameConfig(self, pin_config_dict:dict) -> bool:
        """
        Check if the given pin configurtation truly matches the configuration of the saved pin.

        Parameters:
        pin_config_dict (dict): Configuratien of the pin.

        Returns:
        bool: True if the configuration matches, otherwise False.
        """
        if not pin_config_dict['ptype'] == self.type:
            self.logger.info('Nieuwe "type" {} voor pin {} is anders dan bekend "type" {}'.format(pin_config_dict['ptype'], self.pin, self.type))
            return False
        if not pin_config_dict["active_state"] == self.active_state:
            self.logger.info('Nieuwe "active_state" {} voor pin {} is anders dan bekend "active_state" {}'.format(pin_config_dict["active_state"], self.pin, self.active_state))
            return False
        if not pin_config_dict["pull_up"] == self.pull_up:
            self.logger.info('Nieuwe "pull_up" {} voor pin {} is anders dan bekend "pull_up" {}'.format(pin_config_dict["pull_up"], self.pin, self.pull_up))
            return False
        return True
    
    def SavePin(self, pin_config_dict:dict):
        """
        Save the pin configuration in this object.

        Parameters:
        pin_config_dict (dict): Configuratien of the pin.
        """
        self.pin = pin_config_dict["pin"]  
        self.active_state = pin_config_dict["active_state"] 
        self.pull_up = pin_config_dict["pull_up"]
        self.value = 'onbekend'  
        # if "password" in pin_config_dict:
        #     self.password = pin_config_dict["password"]  
        # else: 
        #     self.password = ""
        if pin_config_dict['webhook'] is not None : 
            self.webhook = pin_config_dict['webhook'] 
    
    def ConfigurePin(self):
        """
        Configure the de GPIO as the rigth type.

        """
        self.pin_device = DigitalInputDevice(pin = self.pin, 
                                             pull_up = self.pull_up,
                                             bounce_time = None) #,
                                            #  active_state = self.active_state, 
                                            #  pin_factory = LGPIOFactory(chip=0))
        self.pin_device.when_activated = self.calback
        self.pin_device.when_deactivated = self.calback
        self.calback()

    def calback(self):
        """
        Callback functie to process state changes of a pin. This is only set for pins that function as an input device. 

        Functie:
        - Adds one to the pin total count.
        - Updates the time of the last count.
        - Checks wether a update is relevant to send (don't want to sent an update every count).
        - In case a webhook was provided, send a POST call to the Home Assistant API with the current pin total count and the rate of change sinds the last update.
        """
        self.count_totaal = self.count_totaal + 1
        self.tijd_laatste_count = time.monotonic()
        if self.is_update_relevant():
            if not self.webhook == "":
                path = 'webhook/{}'.format(self.webhook)
                headers={"Content-Type" : "application/json"}
                data = self.GetPinValue()
                print(json.dumps(data))
                self.HASS_interface.request(path = path, method="POST", headers=headers, data=json.dumps(data))
                # self.logger.info('pin {} updete verstuurd'.format(pin))


    def is_update_relevant(self):
        """
        Controller of er voldoende pulsen geteld of tijd verstreken 
        zijn om een update naar HASS te versturen. 

        Returns:
        bool: True als de update versturen een goed idee is, anders False.
        """
        tot_nog_geteld = self.count_totaal - self.count_laatste_blok
        if tot_nog_geteld == 0:
            self.logger.info('geen counts sinds laatste update')
            return False
        tijd_sinds_laatste_count = time.monotonic() - self.tijd_laatste_count
        print(tot_nog_geteld)
        print(tijd_sinds_laatste_count)
        if tijd_sinds_laatste_count > 60*5: 
            self.logger.info('laatste update langer dan 5 minuten geleden, met nog een rest waarde')
            return True
        elif tijd_sinds_laatste_count > 60 and tot_nog_geteld > 5: 
            self.logger.info('laatste update langer dan 1 minuten geleden, met minimaal 5 counts')
            return True
        elif tijd_sinds_laatste_count > 30 and tot_nog_geteld > 10: 
            self.logger.info('laatste update langer dan 30 seconden geleden, met minimaal 10 counts')
            return True
        elif tijd_sinds_laatste_count > 10 and tot_nog_geteld > 50: 
            self.logger.info('laatste update langer dan 10 seconden geleden, met minimaal 50 counts')
            return True
        elif tot_nog_geteld > 100: 
            self.logger.info('binnen 10 seconden meer dan 100 counts')
            return True
        self.logger.info('geen update nodig')
        return False


    def GetPinValue(self) -> dict:
        """
        Get the current value of a pin.

        Returns:
        dict: The current value of the pin.
        """
        duur =  time.monotonic() - self.tijd_laatste_block
        count_laatste_blok = self.count_totaal - self.count_laatste_blok
        if duur >0.0: 
            self.stroom = count_laatste_blok*1.0/duur/self.calibrationFactor
        else:
            self.stroom = 0


        self.tijd_laatste_block = time.monotonic()
        self.count_laatste_blok = self.count_totaal
        self.logger.info('pin {} heeft {} tellen totaal, met {} tellen laatste {} s, met een stroom van {} per seconde'.format(self.pin, self.count_totaal, count_laatste_blok, duur, self.stroom))
        return {"totaal": self.count_totaal, "stroom": self.stroom}

    def ProcessPinUpdate(self, pin_config_dict:dict) -> bool:
        """
        Process the new optained value of the pin configuration. Gennerally 
        this only works for output pins. Input pins wil only show a log 
        message with their current state.

        Parameters:
        pin_config_dict (dict): Configuratie of the pin.

        Returns:
        bool: True if update succesful, otherwise False.
        """
        if not self.HasSameConfig(pin_config_dict):
            return False
        self.logger.info('pin {} heeft {} tellen totaal, met een stroom van {} per seconde'.format(self.pin, self.count_totaal, self.stroom))
        return True


