# OpenClaw V1 Spec

## /analyze

### Input
- symbol
- optional user query text

### Supported examples
- BTC
- ETH
- SOLUSDT
- /analyze BTCUSDT
- стоит ли шортить SOL
- что по битку
- разбор ETH

### Goal
Дать пользователю понятный и полезный анализ одной монеты в одном сообщении.

Пользователь должен за 5–10 секунд понять:
- что происходит с монетой
- какой сейчас bias
- какие уровни самые важные
- есть ли bullish или bearish сценарий
- есть ли вообще чистый сетап

### Data sources
- exchange market data
- klines by timeframe
- technical indicators
- news context
- internal scoring / reasoning logic

### Internal steps
1. Нормализовать symbol.
2. Получить market data по монете.
3. Получить свечи по нужным таймфреймам.
4. Посчитать базовые индикаторы.
5. Определить short-term и higher-timeframe context.
6. Найти ключевые уровни.
7. Сформировать bullish scenario.
8. Сформировать bearish scenario.
9. Добавить краткий news context.
10. Вернуть один готовый структурированный ответ.

### Output
Ответ должен содержать:
- Header
- Summary
- Bias
- Why
- Key levels
- Bullish scenario
- Bearish scenario
- News context
- Risk note

### Output structure

#### Header
Название модуля и symbol.

Пример:
`🧠 OpenClaw Analysis — BTCUSDT`

#### Summary
1–3 короткие строки с общей картиной.

#### Bias
Одно из значений:
- Bullish
- Bearish
- Neutral
- Mixed
- Bullish-to-neutral
- Bearish-to-neutral

#### Why
2–4 короткие причины, почему bias такой.

#### Key levels
- support
- resistance
- breakout trigger
- breakdown trigger

#### Bullish scenario
- entry logic
- invalidation
- targets

#### Bearish scenario
- entry logic
- invalidation
- targets

#### News context
1–3 строки:
- поддерживают ли новости движение
- нейтральны ли они
- есть ли сильный риск-фактор

#### Risk note
Короткое замечание, если:
- рынок грязный
- структура неясная
- движение уже перегрето
- подтверждения недостаточно

### Output example

```text
🧠 OpenClaw Analysis — BTCUSDT

Summary:
BTC remains constructive on higher timeframes, but short-term momentum is slowing near resistance.

Bias:
Bullish-to-neutral

Why:
- price is holding above key 4H support
- trend structure is still intact
- momentum is cooling near local resistance
- no strong negative news pressure right now

Key Levels:
- Support: 68,200
- Resistance: 69,450
- Breakout trigger: above 69,450
- Breakdown trigger: below 68,200

Bullish Scenario:
- Entry logic: reclaim and hold above 69,450
- Invalidation: back below breakout zone
- Targets: 70,200 / 71,000

Bearish Scenario:
- Entry logic: lose 68,200 with acceptance below
- Invalidation: recovery back above level
- Targets: 67,500 / 66,900

News Context:
Headline flow is neutral-to-mildly supportive. No dominant bearish catalyst detected.

Risk Note:
Short-term structure is compressed near resistance; avoid forcing entries without confirmation.