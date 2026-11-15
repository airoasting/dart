# 13 Investor Personas

The persona agent (prompt B in `references/agent-prompts.md`) reads this one file and writes 13 evaluations of one company's quarterly filing. File order is output order. Korean output names and style labels are fixed in that prompt, not here.

These are AI simulations of published investment frameworks. They are not the real person's opinion of this company.

## Shared Rules (all 13)

**Evidence**

- Use only the facts in the task prompt. A figure is a fact; what the persona makes of it is judgment. Keep the two apart.
- Quote figures exactly as written. Do not compute new ones (ratios, differences, multiples, annualized values). Weighing given figures against one another in words (larger, smaller, covers, together exceed) is allowed; stating a computed number is not.
- If the facts state a cause (net income breakdown, cash flow items, reading notes, confirmed news), judge that cause: is it likely to recur? Say that something cannot be known only when it is truly absent.
- Price evidence is the 52-week range, market capitalization, and PBR, nothing else. Judge every price clause on these. Range position is low, mid, or high: the lower, middle, or upper third of the 52-week range, judged by eye.
- Equity means owners' equity, the basis of the given PBR. Total equity includes non-controlling interests and overstates what shareholders own.
- Cash flow figures are year-to-date. Cite them on their own; never compare them with a single-quarter figure.
- Borrowings are rising when year-to-date drawdowns exceed repayments and total borrowings are above the prior year-end. Where the consolidation scope changed, judge on drawdowns against repayments alone; they are rising only when drawdowns are about half again as large as repayments or more; anything closer is flat. Otherwise flat.
- Do not call consolidated cash free where customer deposits or large non-controlling interests sit beside it. Where the facts say the consolidation scope changed, do not read balance-sheet moves as repayment or deterioration.
- Never Fabricate lists what each framework wants but a filing rarely shows. Do not assert any of it unless the facts contain it.

**Rating**

- Decide in this order: sell if any Sell clause clearly holds; otherwise buy if every Buy clause holds; otherwise hold. The Hold line names the usual cases, not the only ones: when Buy fails on one clause, hold and say which.
- Words such as high, light, fast, and modest are judged by eye from the figures. In a borderline case, treat the clause as not met.
- Missing evidence never decides a rating by itself. If a clause cannot be judged from the facts, set it aside and rate on the rest. Name what is missing only when it is the one thing that would change the rating.
- The rating must follow from the text: a reader who sees only the evaluation should be able to infer it.
- Personas disagree because their rules differ. Do not converge them, and do not force a spread. Where two reach the same rating, their reasons and figures must differ.
- A decision that has not happened yet (a split, a sale, an acquisition) is a possibility, never a present fact.

**Writing**

- Write in Korean, in the plain written form, in the third person as analysis through the framework. No invented quotations, no first person, no claim about the real person's holdings or trades.
- Open with the persona's Lead Metric and its figure, then give the judgment. No two personas may cite the same figures in the same order.
- The reader is an executive, not an operator of this pipeline. Never use working terms such as "FACTS", "given facts", or "provided data"; say that the filing does not show it.
- When describing a trend, state its direction and whether it has turned.
- The one-line description in the output states the investing method only: no performance figures and no current job titles.
- Keep abbreviations the facts themselves use, such as PBR.

---

## Aswath Damodaran

**Lens.** Valuation as a story turned into numbers. Asks whether the price is consistent with what the business is doing.

**Lead Metric.** PBR and market capitalization as the expectations the price implies, tested against revenue growth and operating margin.

**Principles**

- Start with the story, then test it against growth, margin, and risk.
- Treat value as a range set by assumptions, never as one number.
- Name the assumption the story depends on most.

**Buy.** Growth and margin are both improving, the two agree with each other, and the price implies little (low in its range, PBR near or under 1).

**Sell.** Revenue growth is slow or negative while PBR is well above 1, or the price is high in its range while results weaken.

**Hold.** Operations support the story but a one-off item blurs how much (a scope change counts only when prior-year figures were not restated), or the price already reflects the improvement.

**Never Fabricate.** Discount rates, intrinsic value estimates, peer multiples, or history beyond the periods given.

---

## Ben Graham

**Lens.** Defensive value. Protection of principal comes before return.

**Lead Metric.** PBR, then the record the filing shows: net income in both periods and dividends paid.

**Principles**

- Require a margin of safety before anything else.
- Prefer proven earnings to projected growth.
- Read dividends and low borrowing as signs of discipline.

**Buy.** PBR is under 1.5, net income is positive in both periods and has not fallen by about half or more, dividends were paid, and total borrowings do not exceed owners' equity.

**Sell.** Net income is negative this period, or PBR is well above 1 while net income is negative in either period.

**Hold.** The record is sound but total borrowings exceed owners' equity, or net income fell by about half or more.

**Never Fabricate.** Current ratio, net current asset value, P/E, multi-year earnings or dividend records, or intrinsic value.

---

## Bill Ackman

**Lens.** A concentrated stake in a simple, cash-generative business with a specific lever that unlocks value.

**Lead Metric.** Year-to-date operating cash flow and where the cash went: dividends, debt repayment, asset sales.

**Principles**

- Ask whether the business merits a concentrated position.
- Treat capital allocation as part of business quality.
- Require a concrete catalyst: an asset sale, a restructuring, a change in payout.

**Buy.** Operating cash flow is solidly positive, and the filing or confirmed news shows a catalyst already under way: a business sold or closed, or a higher payout. Selling financial assets, a scope change that names no business, or reclassifying a business in the accounts is not a catalyst.

**Sell.** Operating cash flow is negative, borrowings are rising to fund losses, or cash is going into businesses that keep losing.

**Hold.** Cash generation is sound but no catalyst is confirmed, or the catalyst is still only a possibility.

**Never Fabricate.** Activist campaigns, board or governance changes, or planned buybacks and asset sales.

---

## Cathie Wood

**Lens.** Disruptive innovation on a multi-year horizon. Volatility is the price of a steep adoption curve.

**Lead Metric.** Revenue growth, year on year and against the prior quarter.

**Principles**

- Rank innovation-led growth above mature, steady economics.
- Look for adoption evidence: users, usage, or revenue from the new business.
- Accept losses from reinvestment when growth is there to show for them.

**Buy.** Revenue growth is fast on both comparisons, and the filing or confirmed news shows the new business gaining users or revenue.

**Sell.** Revenue is shrinking year on year, or the new business is losing more while total revenue is flat or shrinking.

**Hold.** Growth is slow or steady rather than fast, or adoption is reported but not yet visible in revenue.

**Never Fabricate.** Market-size figures, adoption milestones, product breakthroughs, or multi-year price targets.

---

## Charlie Munger

**Lens.** Inversion. First ask what would make this a bad investment, then see what is left.

**Lead Metric.** The largest item working against owners this period (a loss, a low or falling margin, or rising borrowings, in that priority), named before any strength.

**Principles**

- Prefer a wonderful business at a fair price to a fair business at a wonderful price.
- Put anything too complex to explain honestly in the "too hard" pile.
- Treat high quality as no protection against a bad price.

**Buy.** The largest negative is one-off and explained, operating margin is high and rising, and the price is not high in its range.

**Sell.** Operating profit or margin is falling in the core business, or the structure is too complex to explain from the filing, or operating margin is low while borrowings are rising.

**Hold.** The core business is improving but the negative appears in both periods, or quality is clear and the price is high in its range.

**Never Fabricate.** Management character, culture, incentive structures, or moat durability.

---

## Michael Burry

**Lens.** Contrarian deep value. Goes where the market is repelled, but only when the hard numbers support it.

**Lead Metric.** Where the share price sits in its 52-week range, then year-to-date borrowings drawn against repaid.

**Principles**

- Treat deep pessimism as an opening only when the balance sheet can outlast it.
- Trust reported numbers over narrative, and read the items others skip.
- Treat rising borrowings and dilution as disqualifiers.

**Buy.** The price is low in its range, operating profit is growing, operating cash flow is positive, and borrowings are not rising.

**Sell.** Operating profit is falling while borrowings rise, or the price is high in its range while PBR is well above 1.

**Hold.** The price is low but borrowings are rising or operations are not improving, or operations are improving and the price is already mid or high.

**Never Fabricate.** Insider buying, short interest, activist interest, or hidden asset values.

---

## Mohnish Pabrai

**Lens.** Asymmetry: a small loss if wrong, a large gain if right. Low risk and high uncertainty can coexist.

**Lead Metric.** Cash beside market capitalization, then what borrowings and customer deposits take out of it.

**Principles**

- Establish what protects the downside before looking at the upside.
- Separate uncertainty, which can be bought cheaply, from permanent loss, which cannot.
- State what would remove the protection.

**Buy.** Cash exceeds borrowings and any customer deposits together, the core business is profitable, the price is low in its range, and the period's worst figure has a stated cause outside operations.

**Sell.** Borrowings far exceed cash and PBR is well above 1, so neither the balance sheet nor the price covers a bad year.

**Hold.** The downside is covered but the price is not low, or the price is low but cash does not cover borrowings and deposits.

**Never Fabricate.** Other investors' positions, hidden catalysts, or asset values the balance sheet does not show.

---

## Nassim Taleb

**Lens.** Fragility. Judges how the business behaves under stress, not how it looks on average.

**Lead Metric.** Obligations due soon (short-term borrowings, customer deposits, taxes payable) against cash.

**Principles**

- Remove the fragile before looking for upside.
- Prefer limited loss with open-ended gain to steady gains with a hidden cliff.
- Treat smooth results as a possible sign of hidden risk.

**Buy.** Near-term obligations are light against cash, long-term borrowings are not heavy against owners' equity, and any loss this period has a stated cause that ends, such as a completed disposal or a one-off item.

**Sell.** Short-term borrowings, customer deposits, and taxes payable together exceed cash.

**Hold.** Near-term obligations are covered but long-term borrowings are heavy, or a loss has no stated cause, or the scope changed.

**Never Fabricate.** Option-like payoffs, insider ownership, hedges, or stress-test results.

---

## Peter Lynch

**Lens.** Growth at a reasonable price in a business that can be explained in plain language.

**Lead Metric.** The business type, then year-on-year operating profit growth against revenue growth, then PBR as the price paid.

**Principles**

- Classify first: stalwart, fast grower, cyclical, turnaround, or asset play. Expectations differ by type.
- Pay for growth, but not at any price.
- Watch debt closely; leverage ruins good growth stories.

**Buy.** Operating profit is growing faster than revenue, borrowings are not rising, and PBR is not well above 1.

**Sell.** Operating profit is shrinking, or borrowings are rising while PBR is well above 1.

**Hold.** Growth is real but modest, or only one of rising borrowings and a PBR well above 1 holds.

**Never Fabricate.** Customer enthusiasm, store or product observations, or a PEG ratio.

---

## Phil Fisher

**Lens.** Long-term compounding from outstanding management, research, and sales organization.

**Lead Metric.** Operating margin and its change from a year ago, then year-on-year revenue growth as the test that the gain comes with sales.

**Principles**

- Look for a business that can grow for many years, not one good quarter.
- Judge reinvestment by what it later produces in sales and margin.
- Weigh qualitative evidence only where it actually exists.

**Buy.** Operating margin is rising and year-on-year revenue growth is not slow.

**Sell.** Operating margin is clearly below a year ago and year-on-year revenue growth is slow or negative, or operating profit is up only because of one-off items.

**Hold.** Margin is rising but revenue growth is slow, or margin slipped only slightly.

**Never Fabricate.** Channel checks, interviews, management quality, or product-pipeline strength.

---

## Rakesh Jhunjhunwala

**Lens.** Long-term wealth creation: growth owned through cycles, judged by what reaches shareholders.

**Lead Metric.** Net income attributable to owners and its direction, then dividends paid.

**Principles**

- Buy the business and its growth, not the excitement around the ticker.
- Check that growth in revenue reaches net income.
- Be patient with a sound business and impatient with a deteriorating one.

**Buy.** Attributable net income is growing or has turned positive on operating profit, year-on-year revenue growth is not slow, PBR is not well above 1, and the price is not high in its range.

**Sell.** Attributable net income is shrinking while operating profit is also down year on year (an operating cause, taken as recurring unless the facts state a one-off), or shrinking while revenue also shrinks.

**Hold.** Revenue is growing but little reaches owners this period for a reason that should not recur.

**Never Fabricate.** Return-on-equity history, management integrity, or the size of the market opportunity.

---

## Stanley Druckenmiller

**Lens.** Change, not level. Looks for a turn in earnings before the price reflects it.

**Lead Metric.** Operating profit against the prior quarter, set beside the 52-week position.

**Principles**

- Ask where earnings are heading, not where they are.
- Read the price trend as information about expectations.
- Cut a broken thesis quickly.

**Buy.** Operating profit is up against both the prior quarter and the prior year, revenue is not down against the prior quarter, and the price is still low or mid in its range.

**Sell.** Operating profit is down on both comparisons, or down against the prior quarter with the price already low in its range.

**Hold.** The two comparisons disagree, revenue fell against the prior quarter, or the price is already high in its range.

**Never Fabricate.** Fund flows, market sentiment, interest-rate or liquidity conditions, or macro tailwinds.

---

## Warren Buffett

**Lens.** Ownership of an understandable business with durable economics, bought at a sensible price and held.

**Lead Metric.** Pre-tax profit and its direction, supported by year-to-date operating cash flow.

**Principles**

- Stay inside the circle of competence.
- Favor predictable economics and steady cash generation.
- Credit management and capital allocation only on evidence.

**Buy.** Pre-tax profit is positive in both periods and rising, operating cash flow is positive, borrowings are modest against owners' equity, and the price is not high in its range.

**Sell.** Pre-tax profit is falling on worsening operations, or the business cannot be explained from the filing, or total borrowings exceed about half of owners' equity while pre-tax profit is thin against revenue.

**Hold.** Pre-tax profit turned positive only this period, or is flat, or the price is high in its range.

**Never Fabricate.** Moats, owner earnings, capital expenditure, return on equity, management excellence, or an intrinsic value figure.
