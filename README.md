# Drink Counter Integration

This is a custom integration for [Home Assistant](https://www.home-assistant.io/) distributed via HACS.

The integration allows you to manage drink tallies for multiple users. You can define drinks with prices and increment counters using a service call.

## Features

- Configure users via the UI and add drinks individually with a name and price.
- Sensor entities for each drink and a sensor showing the total amount a user has to pay.
- Button entity to reset all counters for a user.
- Service `drink_counter.add_drink` to add a drink for a user.

## Installation

1. Add this repository to HACS as a custom repository.
2. Install the **Drink Counter** integration.
3. Restart Home Assistant and add the integration via the integrations page.
   The integration is fully configurable through the UI.

## Usage

After adding a user, the setup will prompt you to enter drinks with their prices one after another. Once configured, call the service `drink_counter.add_drink` with parameters `user` and `drink` to increment the counter. Use the reset button entity to reset all counters.
