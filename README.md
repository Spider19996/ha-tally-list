# Tally List Integration

🇩🇪 [Deutsche Version lesen](README.de.md)

This custom integration for [Home Assistant](https://www.home-assistant.io/) is distributed via HACS and helps you manage drink tallies for multiple persons. All persons with a linked Home Assistant user account are imported automatically. Drinks are defined once and shared across everyone.

## Features

- Automatic import of persons with user accounts.
- Shared drink list with name and price for every person.
- Sensor entities for drink counts, drink prices, a free amount, and the total amount due per person.
- Button entity to reset a person's counters; only users with override permissions ("Tally Admins") can use it.
- Configurable currency symbol (defaults to €).
- Services to add, remove, adjust, reset and export tallies, and set personal PINs.
- Counters cannot go below zero when removing drinks.
- Option to exclude persons from automatic import.
- Grant override permissions to selected users so they can tally drinks for everyone.
- Public devices can tally drinks for everyone when the target user's PIN is provided.
- Optional free drinks mode with a dedicated user, log feed sensors and configurable name.

## Installation

1. Add this repository to HACS as a custom repository.
2. Install the **Tally List** integration.
3. Restart Home Assistant and add the integration via the integrations page.

It is recommended to also install the companion [Tally List Lovelace card](https://github.com/Spider19996/ha-tally-list-lovelace) for a matching dashboard interface.

## Usage

At initial setup you will be asked to enter available drinks. All persons with a user account share this list. Drinks and prices can later be managed from the integration options.

### Services

- `tally_list.add_drink`: increment drink count for a person (fails if the person does not exist; optionally specify amount).
- `tally_list.remove_drink`: decrement drink count for a person (never below zero; optionally specify amount).
- `tally_list.adjust_count`: set a drink count to a specific value.
- `tally_list.reset_counters`: reset all counters for a person or for everyone if no user is specified.
- `tally_list.export_csv`: export all `_amount_due` sensors to CSV files (`daily`, `weekly`, `monthly`, or `manual`) saved under `/config/backup/tally_list/<type>/`.
- `tally_list.set_pin`: set or clear your personal PIN required for public devices.

### Reset Button

Each person gets a `button.<person>_reset_tally` entity to reset all their counters. Only Tally Admins can press it.

## Price List and Sensors

All drinks are stored in a single price list. A dedicated user named `Preisliste` (`Price list` in English) exposes one price sensor per drink as well as a free amount sensor, while regular persons only get count and total amount sensors. The free amount is subtracted from each person's total. You can edit drinks, prices and the free amount at any time from the integration options.
Sensors for the price list user always use English entity IDs prefixed with `price_list`, for example `sensor.price_list_free_amount` or `sensor.price_list_wasser_price`.

## Free Drinks (Optional)

If enabled in the integration options, complimentary drinks are tracked separately.
A dedicated user (default name `Free Drinks`, configurable) records all free
drinks and exposes the same count and amount sensors as regular users, for
example `sensor.free_drinks_beer_count` and `sensor.free_drinks_amount_due`.
Each free drink entry is written to a CSV log under
`/config/backup/tally_list/free_drinks/`. For every year a feed sensor such as
`sensor.free_drink_feed_2024` is created that shows the latest log entry and
lists recent free drinks in its attributes.

You can activate or deactivate the feature and change the free drinks user name
from the integration options.

## WebSocket API

The WebSocket command `tally_list/get_admins` returns all users that currently have override permissions and can be called from the Home Assistant frontend or an external client. The command requires an authenticated Home Assistant user.

```js
await this.hass.connection.sendMessagePromise({ type: "tally_list/get_admins" });
```

Example response:

```json
{"id":42,"type":"result","success":true,"result":{"admins":["tablet_dashboard","Test","Test 2"]}}
```

The command `tally_list/is_public_device` returns whether the authenticated user is configured as a public device:

```js
await this.hass.connection.sendMessagePromise({ type: "tally_list/is_public_device" });
```

Example response:

```json
{"id":42,"type":"result","success":true,"result":{"is_public":true}}
```
