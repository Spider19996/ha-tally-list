# Tally List Integration

🇩🇪 [Deutsche Version lesen](README.de.md)

This custom integration for [Home Assistant](https://www.home-assistant.io/) is distributed via HACS and helps you manage drink tallies for multiple persons. All persons with a linked Home Assistant user account are imported automatically. Drinks are defined once and shared across everyone.

## Features

- Automatic import of persons with user accounts.
- Shared drink list with name and price for every person.
- Sensor entities for drink counts, drink prices, a free amount, and the total amount due per person.
- Button entity to reset a person's counters; only users with override permissions ("Tally Admins") can use it.
- Configurable currency symbol (defaults to €).
- Services to add, remove, adjust, reset and export tallies.
- Counters cannot go below zero when removing drinks.
- Option to exclude persons from automatic import.
- Grant override permissions to selected users so they can tally drinks for everyone.

## Installation

1. Add this repository to HACS as a custom repository.
2. Install the **Tally List** integration.
3. Restart Home Assistant and add the integration via the integrations page.

It is recommended to also install the companion [Tally List Lovelace card](https://github.com/Spider19996/ha-tally-list-lovelace) for a matching dashboard interface.

## Usage

At initial setup you will be asked to enter available drinks. All persons with a user account share this list. Drinks and prices can later be managed from the integration options.

### Services

- `tally_list.add_drink`: increment drink count for a person.
- `tally_list.remove_drink`: decrement drink count for a person (never below zero).
- `tally_list.adjust_count`: set a drink count to a specific value.
- `tally_list.reset_counters`: reset all counters for a person or for everyone if no user is specified.
- `tally_list.export_csv`: export all `_amount_due` sensors to CSV files (`daily`, `weekly`, `monthly`, or `manual`) saved under `/config/backup/tally_list/<type>/`.

### Reset Button

Each person gets a `button.<person>_reset_tally` entity to reset all their counters. Only Tally Admins can press it.

## Price List and Sensors

All drinks are stored in a single price list. A dedicated user named `Preisliste` (`Price list` in English) exposes one price sensor per drink as well as a free amount sensor, while regular persons only get count and total amount sensors. The free amount is subtracted from each person's total. You can edit drinks, prices and the free amount at any time from the integration options.
Sensors for the price list user always use English entity IDs prefixed with `price_list`, for example `sensor.price_list_free_amount` or `sensor.price_list_wasser_price`.

## WebSocket API

The WebSocket command `tally_list/get_admins` returns all users that currently have override permissions and can be called from the Home Assistant frontend or an external client. The command requires an authenticated Home Assistant user.

```js
await this.hass.connection.sendMessagePromise({ type: "tally_list/get_admins" });
```

Example response:

```json
{"id":42,"type":"result","success":true,"result":{"admins":["tablet_dashboard","Test","Test 2"]}}
```
