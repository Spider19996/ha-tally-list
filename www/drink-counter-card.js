class DrinkCounterCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 16px;
        }
        h3 {
          margin: 8px 0;
        }
        ul {
          list-style: none;
          padding: 0;
        }
        li {
          display: flex;
          align-items: center;
          margin: 4px 0;
        }
        button {
          margin-left: 8px;
        }
      </style>
      <div id="content"></div>
    `;
    this._content = this.shadowRoot.getElementById('content');
    this.shadowRoot.addEventListener('click', (ev) => {
      const target = ev.target;
      if (target.dataset.drink) {
        this._hass.callService('drink_counter', 'add_drink', {
          user: target.dataset.user,
          drink: target.dataset.drink,
        });
      } else if (target.dataset.reset) {
        this._hass.callService('drink_counter', 'reset_counters', {
          user: target.dataset.reset,
        });
      }
    });
  }

  setConfig(config) {
    this._config = Object.assign({ title: 'Drink Counter' }, config);
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._content) return;
    const prices = {};
    Object.values(hass.states).forEach((st) => {
      const name = st.attributes.friendly_name;
      if (
        st.entity_id.startsWith('sensor.') &&
        name &&
        name.startsWith('Preisliste') &&
        name.endsWith('Price')
      ) {
        const drink = name.substring('Preisliste '.length, name.length - 6);
        prices[drink] = parseFloat(st.state);
      }
    });
    const users = {};
    Object.values(hass.states).forEach((st) => {
      const name = st.attributes.friendly_name;
      if (!name || !st.entity_id.startsWith('sensor.')) return;
      if (name.endsWith('Count')) {
        const parts = name.split(' ');
        const user = parts.shift();
        if (user === 'Preisliste') return;
        const drink = parts.slice(0, -1).join(' ');
        users[user] = users[user] || { drinks: {} };
        users[user].drinks[drink] = parseInt(st.state, 10);
      } else if (name.endsWith('Amount Due')) {
        const user = name.substring(0, name.length - ' Amount Due'.length);
        if (user === 'Preisliste') return;
        users[user] = users[user] || { drinks: {} };
        users[user].amount = st.state;
      }
    });
    let html = `<h2>${this._config.title}</h2>`;
    Object.keys(users).forEach((user) => {
      const data = users[user];
      html += `<h3>${user} - ${data.amount || '0'} €</h3>`;
      html += '<ul>';
      Object.keys(prices).forEach((drink) => {
        const count = data.drinks[drink] || 0;
        const total = (count * (prices[drink] || 0)).toFixed(2);
        html += `<li>${drink}: ${count} (${total} €)`;
        html += ` <button data-user="${user}" data-drink="${drink}">+</button></li>`;
      });
      html += '</ul>';
      html += `<button data-reset="${user}">Reset</button>`;
    });
    this._content.innerHTML = html;
  }

  getCardSize() {
    return 3;
  }
}

customElements.define('drink-counter-card', DrinkCounterCard);
