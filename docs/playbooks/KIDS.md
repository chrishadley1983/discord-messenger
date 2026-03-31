# Kids Playbook

## IHD Dashboard (Interactive Household Dashboard)

Base URL: `http://192.168.0.110:3000`

## Pocket Money

Children: `emmie`, `max`. Amounts are in **pence**.

### Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/kids/pocket-money/calculate?week=YYYY-MM-DD` | Calculate weekly grid totals |
| GET | `/api/kids/pocket-money/summary` | Current balances for both children |
| GET | `/api/kids/pocket-money/grid?week=YYYY-MM-DD` | Weekly grid ticks (room tidy, behaviour, homework, boost) |
| GET | `/api/kids/pocket-money` | Full balance + transaction history |
| POST | `/api/kids/pocket-money` | Credit or debit a child's balance |

### Credit/Debit Body

```json
{
  "child": "emmie",
  "amount": 321,
  "category": "pocket_money",
  "description": "Week of 23 Mar — pocket money",
  "source": "peter"
}
```

### Rates

- Room Tidy: 40p/day
- Behaviour: 20p/day
- Homework: 20p/day
- Special Boost: £2.00/day (rare)

### Rules

- Always confirm new balances after crediting
- If Chris says a flat amount (e.g. "add 3.21 each"), convert to pence and POST for each child
- If the grid is empty, mention it needs filling in on the dashboard first
- Keep the tone warm — this is a fun family thing
