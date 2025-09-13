# Tally List Integration

🇩🇪 [Deutsche Version lesen](README.de.md)

This custom integration for [Home Assistant](https://www.home-assistant.io/) is distributed via HACS and helps you manage drink tallies for multiple persons. All persons with a linked Home Assistant user account are imported automatically. Drinks are defined once and shared across everyone.

## Features 

- Automatic import of persons with user accounts.
- Shared drink list with name and price for every person.
- Sensor entities for drink counts, drink prices, a free amount, a personal credit balance, and the total amount due per person.
- Button entity to reset a person's counters; only users with override permissions ("Tally Admins") can use it.
- Configurable currency symbol (defaults to €).
- Services to add, remove, adjust, reset and export tallies, and manage personal PINs (Tally Admins can set PINs for other users).
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
- `tally_list.export_csv`: export all `_amount_due` sensors to CSV files (`daily`, `weekly`, `monthly`, or `manual`) saved under `/config/tally_list/<type>/`.
- `tally_list.set_pin`: set or clear a personal 4-digit numeric PIN required for public devices (admins can set PINs for others).
- `tally_list.add_credit`: increase credit for a person.
- `tally_list.remove_credit`: decrease credit for a person.
- `tally_list.set_credit`: set credit for a person to an exact amount.

### Reset Button

Each person gets a `button.<person>_reset_tally` entity to reset all their counters. Only Tally Admins can press it.

### Credit

Every person also has a `sensor.<person>_credit` entity that stores their available credit. Positive credit reduces the `*_amount_due` sensor; negative credit increases it. Adjust credit through the `tally_list.add_credit`, `tally_list.remove_credit`, and `tally_list.set_credit` services.

## Price List and Sensors

All drinks are stored in a single price list. A dedicated user named `Preisliste` (`Price list` in English) exposes one price sensor per drink as well as a free amount sensor, while regular persons get count, credit and total amount sensors. The free amount and personal credit are subtracted from each person's total. You can edit drinks, prices and the free amount at any time from the integration options.
Sensors for the price list user always use English entity IDs prefixed with `price_list`, for example `sensor.price_list_free_amount` or `sensor.price_list_wasser_price`.

Every change to the price list is written to yearly CSV logs under `/config/tally_list/price_list/`. A feed sensor `sensor.price_list_feed` shows the latest entry and exposes recent changes in its attributes.

## Free Drinks (Optional)

If enabled in the integration options, complimentary drinks are tracked separately.
A dedicated user (default name `Free Drinks`, configurable) records all free
drinks and exposes the same count and amount sensors as regular users, for
example `sensor.free_drinks_beer_count` and `sensor.free_drinks_amount_due`.
Each free drink entry is written to yearly CSV files `free_drinks_<year>.csv`
under `/config/tally_list/free_drinks/`. A feed sensor
`sensor.free_drink_feed` shows the latest log entry and lists recent free drinks
in its attributes.

You can activate or deactivate the feature and change the free drinks user name
from the integration options.

## WebSocket API

The WebSocket command `tally_list/get_admins` returns all users that currently have override permissions and can be called from the Home Assistant frontend or an external client. The command requires an authenticated Home Assistant user.

```js
await this.hass.callWS({ type: "tally_list/get_admins" });
```

Example response:

```json
{"admins":["tablet_dashboard","Test","Test 2"]}
```

The command `tally_list/is_public_device` returns whether the authenticated user is configured as a public device:

```js
await this.hass.callWS({ type: "tally_list/is_public_device" });
```

Example response if the user is configured as a public device:

```json
{"is_public": true}
```

Example response for a regular user:

```json
{"is_public": false}
```

Public devices can authenticate a user once via the `tally_list/login` command so that subsequent service calls no longer need the `pin` parameter:

```js
await this.hass.callWS({ type: "tally_list/login", user: "Alice", pin: "1234" });
```

Example success response:

```json
{"success": true}
```

To end the session call `tally_list/logout`:

```js
await this.hass.callWS({ type: "tally_list/logout" });
```
