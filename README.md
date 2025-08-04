# Tally List Integration

This is a custom integration for [Home Assistant](https://www.home-assistant.io/) distributed via HACS.

The integration allows you to manage drink tallies for multiple persons from Home Assistant's Person integration. All persons that have a linked Home Assistant user account are imported automatically. Drinks are defined once and shared across all persons. Counters start at zero and can be adjusted using services.

## Features

- Persons with user accounts are added automatically. Drinks are added only once with a name and price and are available for every person.
- Sensor entities for each drink's count, each drink's price, a free amount sensor, and a sensor showing the total amount a person has to pay.
- Button entity to reset all counters for a person. Only users with
  override permissions ("Tally Admins") can press it.
- Currency symbol is configurable (defaults to €).
- Service `tally_list.add_drink` to add a drink for a person.
- Service `tally_list.remove_drink` to remove a drink for a person.
- Service `tally_list.adjust_count` to set a drink count to a specific value.
- Service `tally_list.export_csv` to export all amount_due sensors to a CSV file, sorted alphabetically by name.
- Counters cannot go below zero when removing drinks.
- Exclude persons from automatic import via the integration options.
- Grant override permissions to selected users so they can tally drinks for
  everyone.

## Installation

1. Add this repository to HACS as a custom repository.
2. Install the **Tally List** integration.
3. Restart Home Assistant and add the integration via the integrations page.
   The integration is fully configurable through the UI.

## Usage

When the integration is first set up, all persons with a user account are added and you will be asked to enter the available drinks. All further persons will automatically use this list. Drinks can later be managed from the integration options where you can add, remove or edit their prices. Call the service `tally_list.add_drink` with parameters `user` and `drink` to increment the counter. Use `tally_list.adjust_count` with `count` to set an exact value. To decrement by one call `tally_list.remove_drink` with `user` and `drink`. Only Tally Admins can use the reset button entity to reset all counters. The reset button entity ID follows `button.<person>_reset_tally`, so you can match all reset buttons with `button.*_reset_tally`.
Call `tally_list.export_csv` to create a CSV snapshot of all `_amount_due` sensors sorted alphabetically by name. The file is stored as `amount_due_YYYY-MM-DD_HH-MM.csv` inside `/config/backup/tally_list/`.

## Price List and Sensors

All drinks are stored in a single price list. A dedicated user named
`Preisliste` is automatically created when the integration is first set up. This user
exposes one price sensor per drink as well as a free amount sensor while regular
persons only get count and total amount sensors. The free amount is subtracted from
each person's total. You can edit the drinks, prices and free amount at any time
from the integration options.

## WebSocket API

The integration exposes a WebSocket command `tally_list/get_admins`. It returns
all users that currently have override permissions and can be called from a
Home Assistant frontend or external client. The command requires an
authenticated Home Assistant user.

```js
await this.hass.connection.sendMessagePromise({ type: "tally_list/get_admins" });
```

The response contains the usernames in an array and includes the WebSocket metadata:

```json
{"id":42,"type":"result","success":true,"result":{"admins":["tablet_dashboard","Test","Test 2"]}}
```

## Acknowledgements

This entire script was generated with the help of ChatGPT / Codex.
