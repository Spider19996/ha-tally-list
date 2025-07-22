# Drink Counter Integration

This is a custom integration for [Home Assistant](https://www.home-assistant.io/) distributed via HACS.

The integration allows you to manage drink tallies for multiple persons from Home Assistant's Person integration. Drinks are defined once and shared across all persons. Counters start at zero and can be adjusted using services.

## Features

- Select persons via the UI. Drinks are added only once with a name and price and are available for every person.
- Sensor entities for each drink's count, each drink's price, a free amount sensor, and a sensor showing the total amount a person has to pay.
- Button entity to reset all counters for a person.
- Service `drink_counter.add_drink` to add a drink for a person.
- Service `drink_counter.remove_drink` to remove a drink for a person.
- Service `drink_counter.adjust_count` to set a drink count to a specific value.
- Counters cannot go below zero when removing drinks.

## Installation

1. Add this repository to HACS as a custom repository.
2. Install the **Drink Counter** integration.
3. Restart Home Assistant and add the integration via the integrations page.
   The integration is fully configurable through the UI.

## Usage

When the first person is selected you will be asked to enter the available drinks. All further persons will automatically use this list. Drinks can later be managed from the integration options where you can add, remove or edit their prices. Call the service `drink_counter.add_drink` with parameters `user` and `drink` to increment the counter. Use `drink_counter.adjust_count` with `count` to set an exact value. To decrement by one call `drink_counter.remove_drink` with `user` and `drink`. Use the reset button entity to reset all counters.

## Price List and Sensors

All drinks are stored in a single price list. A dedicated user named
`Preisliste` is automatically created when the first person is set up. This user
exposes one price sensor per drink as well as a free amount sensor while regular
persons only get count and total amount sensors. The free amount is subtracted from
each person's total. You can edit the drinks, prices and free amount at any time
from the integration options.
