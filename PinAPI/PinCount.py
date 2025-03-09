#!/usr/bin/env python
# encoding: utf-8
"""
Generieke pin configurator class

Jeroen van Oosterhout, 15-07-2024
"""
from PinAPI.Pin import *

class Pin_count(Pin):
    def __init__(self, config:PinModel):
        super().__init__(config=config)
        self.count_totaal = 0
        self.tijd_laatste_count = time.monotonic()
        self.count_laatste_blok = 0 
        self.tijd_laatste_block = time.monotonic()
        self.stroom = 0 # pulsen per minut

        self.calibrationFactor = 1 #6.6


    def HasSameConfig(self, config:PinModel) -> bool:
        """
        Check if the given pin configurtation truly matches the configuration of the saved pin.

        Parameters:
        config (Pin): Configuratien of the pin.

        Returns:
        bool: True if the configuration matches, otherwise False.
        """
        if not config.ptype == self.config.ptype:
            self.logger.warning('New "ptype" {} for pin {} is different from known "ptype" {}'.format(config.ptype, self.config.pin, self.config.ptype))
            return False
        if not config.active_state == self.config.active_state:
            self.logger.warning('New "active_state" {} for pin {} is different from known "active_state" {}'.format(config.active_state, self.config.pin, self.config.active_state))
            return False
        if not config.pull_up == self.config.pull_up:
            self.logger.warning('New "pull_up" {} for pin {} is different from known "pull_up" {}'.format(config.pull_up, self.config.pin, self.config.pull_up))
            return False
        return True
        
    def ConfigurePin(self):
        """
        Configure the de GPIO as the rigth type.

        """
        self.pin_device = DigitalInputDevice(pin = self.config.pin, 
                                             pull_up = self.config.pull_up,
                                             bounce_time = None) #,
                                            #  active_state = self.config.active_state, 
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
 
        self.sendWebhook(self.GetPinValue())
 

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
        self.logger.info('pin {} has {} counts total, with {} counts the last {} s, and a flow of {} per second'.format(self.config.pin, self.count_totaal, count_laatste_blok, duur, self.stroom))
        return {"totaal": self.count_totaal, "stroom": self.stroom}

    def ProcessPinUpdate(self, config:PinModel) -> bool:
        """
        Process the new optained value of the pin configuration. Gennerally 
        this only works for output pins. Input pins wil only show a log 
        message with their current state.

        Parameters:
        config (Pin): Configuratie of the pin.

        Returns:
        bool: True if update succesful, otherwise False.
        """
        self.logger.info('pin {} heeft {} tellen totaal, met een stroom van {} per seconde'.format(self.config.pin, self.count_totaal, self.stroom))
        return True


