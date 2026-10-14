# Does this app make sense? An outside check

Written 7 October 2026. I searched the web and opened the sources myself where I could. Each claim below says how far I verified it. Where the evidence does not support the app, or the app contradicts it, that is reported in section 5.

## 1. Verdict

| | |
|---|---|
| **The problem is real and documented** | RMs spend a minority of their time with clients; merchants do leave acquirers, and replacing one is costly; UAE SMEs matter to the economy. |
| **The approach is reasonable** | A decision-support tool that recommends and leaves the decision to the RM matches the Central Bank of the UAE's February 2026 AI guidance. Grounding model answers in data and refusing when unsure is the direction banking research points. |
| **The interchange side of the rate model checks out** | Our interchange table matches Visa's own UAE schedule, with one wrong date in our documents. |
| **The app is not proven to help** | No source tests this app or anything like it for UAE merchant RMs. The uplift figures in the literature are from other settings, mostly vendors and consultants, and I did not verify most of them. |
| **Two things in the app do not hold up** | The "revenue" used for ranking is gross merchant fees, more than half of which is paid out as interchange. And the rate suggestions are lopsided: 93 reductions and 17 increases, which would give away about 29% of the net margin if all were applied. Details in section 5. |

## 2. The problem is real

| Claim | Evidence | How I checked it |
|---|---|---|
| RMs spend only a minority of their time with clients | "In many commercial banks, relationship managers spend just 25 to 30 percent of their time in client dialogue" ([McKinsey, "Agentic AI is here: is your bank's frontline team ready?"](https://www.mckinsey.com/industries/financial-services/our-insights/agentic-ai-is-here-is-your-banks-frontline-team-ready)) | A search extract of the McKinsey page, and Backbase's article citing the same McKinsey page with the same figure. **The McKinsey page itself timed out when I tried to open it.** It covers commercial banking in general, not UAE merchant RMs. |
| Merchants leave their acquirer at a meaningful rate | "The national attrition rate currently stands between 12% and 15%" (Mukesh Gidwani, [PaymentsJournal, 19 July 2018](https://www.paymentsjournal.com/solving-the-merchant-attrition-problem/)). "More than 20 percent of merchants are likely to move from their current provider," 16–17% of it voluntary and possibly preventable (Rajesh Kamath, [ProSight Financial Association, 5 September 2017](https://www.prosightfa.org/insights/merchant-attrition-to-merchant-addition-analytics-as-a-payments-catalyst/)) | Opened both. **Both are US-focused and 8 to 9 years old.** |
| Replacing a lost merchant is expensive | "It takes roughly three new merchant clients to make up for each one that leaves" (ProSight, same article) | Opened it. Same limits. |
| Merchants leave mainly over service and price | PaymentsJournal lists service dissatisfaction, "their costs to be too high", and a competitor promising a better solution | Opened it. |
| UAE SMEs matter | The Minister of Economy said SMEs numbered 557,000 at the end of 2022 and "account for 63.5 per cent of non-oil GDP" ([Gulf News, 6 April 2023](https://gulfnews.com/amp/business/557000-smes-operated-in-uae-at-end-of-2022-minister-of-economy-1.94976713)) | Opened it. |

**What this supports:** the churn-risk and attention sections target a documented problem. **What it does not support:** the size of the benefit for this portfolio.

## 3. The approach is reasonable

| Claim | Evidence | How I checked it |
|---|---|---|
| A fall in transaction volume is a recognised churn warning | "Any reduction in transaction patterns, whether by volume or amount, is thought to indicate the likelihood of their leaving" (ProSight) | Opened it. **But the same article says it is "definitely not the only, best or earliest one."** See section 5. |
| RMs want an assistant that answers questions over their own data | Morgan Stanley's financial-advisor teams are reported to have a 98% adoption rate of its AI assistant, and one advisor in the pilot said it saves 30 minutes per meeting ([CDO Magazine](https://www.cdomagazine.tech/aiml/98-of-morgan-stanley-wealth-management-advisors-use-its-ai-chatbot-with-improved-productivity-cao-explains-how); [CNBC, 26 June 2024](https://www.cnbc.com/2024/06/26/morgan-stanley-openai-powered-assistant-for-wealth-advisors.html)) | **Search extracts only, not opened.** It is wealth management, not merchant banking. It shows demand for the pattern, not that this app works. |
| UAE banks are investing in generative AI | Emirates NBD announced a generative-AI programme with Microsoft ([Gulf News](https://gulfnews.com/business/banking/emirates-nbd-embraces-ai-to-boost-productivity-1.96863997)); ADCB launched an AI-powered mobile app; Mashreq runs an AI assistant for customers | Search extracts. **I found no public example of a merchant-RM co-pilot at a UAE bank.** That is an absence of results from a limited search, not proof none exists. |
| Grounded answers with refusal are the direction for banking AI | A 2026 paper on a banking question-answering model reports "grounded responses with citations", a calibrated "I don't know" mechanism, and deployment "at 40+ financial institutions" ([FinRAG-12B, arXiv 2605.05482](https://arxiv.org/abs/2605.05482), submitted 6 May 2026) | Opened the abstract. The deployment figures are the authors' own claims. |
| Guardrails that screen inputs and outputs are a standard pattern | NVIDIA NeMo Guardrails describes "input, retrieval, dialog, execution, and output rails" at different stages of an LLM interaction ([NVIDIA documentation](https://docs.nvidia.com/nemo/guardrails/latest/index.html)) | Opened it. The page did not define hallucination checks in detail. |

## 4. The controls line up with the regulator, and the local model has a basis

**Central Bank of the UAE, AI guidance, 23 February 2026.** Reported by [The National](https://www.thenationalnews.com/business/banking/2026/02/23/uae-central-bank-issues-new-guidelines-on-the-use-of-ai-in-financial-sector/) (opened) and in the search results of several outlets. The Central Bank's own rulebook page returned "403 Forbidden" and its press-release link returned "404", so I did not read the primary text.

| What the guidance asks | What the app does | Gap |
|---|---|---|
| Human oversight, including a human who "retains full authority to approve or reject outcomes" (search extract) | The co-pilot recommends and explains; it refuses to approve, send, change or book | None for this point |
| Transparency about the use of AI | Every reply is labelled AI-generated or data-only; each suggestion is tagged AI or Rules | None for this point |
| Explainability | The "Why this?" panel shows the data and the checks | Consumers can request an explanation; this app is RM-facing, so that does not directly apply |
| A "documented governance framework"; board and senior management accountable | An audit log and improvement notes exist | **No governance framework or accountable owner is documented.** That is organisational, not something the code can supply |
| Data management and privacy | The data is synthetic; the default model is local | See below |

The guidance is described as guidance, not law. It is aimed at consumer protection, and this is an internal RM tool, so how much of it applies is a question for the bank's compliance team.

**Data localisation (search extracts of the Central Bank rulebook, Al Tamimi and Lexology; not opened).** The Central Bank's Outsourcing Regulation (Circular 14/2021) is described as requiring data localisation within the UAE and a "master system of record" kept in the UAE. Its consumer-protection regime is described as requiring consumer and transaction data to be held in the UAE. If that reading is right, it explains why a local model is the default here. **It also means the optional hosted-model path (Anthropic) should not be used with real client data without legal sign-off.**

**Interchange.** Visa's own schedule, extracted from the PDF itself ("Visa United Arab Emirates Interchange Reimbursement Fees", effective **19 October 2024**, file dated 25 September 2024, [PDF](https://ae.visamiddleeast.com/content/dam/VCOM/regional/cemea/unitedarabemirates/home-page/support-consumer/visa-uae-interchange-reimbursement-fees-19-october-2024.pdf)):

| Item | Visa's figure | Our model uses |
|---|---|---|
| Credit, Classic and Gold | 1.15% | 1.15% (Mass) |
| Credit, Platinum | 1.80% | 1.80% (Premium) |
| Credit, Signature and Infinite | 2.05% and 2.10% | 2.10% (Super Premium) |
| Commercial cards | Visa Business 2.00%, Platinum Business 2.05% | 2.05% (Business, the upper of the two) |
| Debit, Classic to Platinum | 0.75%, cap AED 37.50 | blended 0.80% |
| Debit, Signature and above | 1.00%, cap AED 50 | blended 0.80% |
| Supermarket, credit | 1.05% | 1.05% |
| Education and rental, credit and debit | 0.65% (debit cap AED 32.50) | 0.65%, cap AED 32.50 |

The table matches, apart from the choice of the upper commercial rate. Visa also states, in line with how the model is built: "Merchants do not pay interchange reimbursement fees; merchants pay a 'merchant discount rate' to their acquirer… interchange may only be one component." A trade article reports that the Central Bank introduced a cap on interchange on 1 October 2024 ([Finance Middle East](https://www.financemiddleeast.com/opinion/cutting-payment-costs-a-new-chapter-for-uae-merchants/), opened), which fits the lower debit rates.

## 5. What does not make sense, or is not supported

These are findings against our own work. They are listed in order of how much they matter.

**1. The rate suggestions are lopsided and would cost real margin if applied.**
Of 150 merchants, the model recommends cutting the rate for 93, raising it for 17, and holding 40. Applying every cut would give away about **AED 185,000 a month in merchant fees, 13% of gross fees and 29% of the net margin after interchange**. The 17 increases would add about AED 2,400. Nothing in the app tells the RM what a cut costs. This looks like an artefact of the synthetic data: the invented "current" rates sit above the model's rates for most merchants, so the model mostly says "reduce". It should not be read as evidence that real merchants are overcharged. PaymentsJournal lists cost concerns among the three main reasons merchants leave, but also argues that fixing root causes beats reacting to indicators, and our own churn step already says "call before any pricing action". The rate cards (the Profile card, and the rate wording in chat and flags) do not.
*Not done yet: a profitability check and a margin floor on a reduction.*

**2. "Estimated monthly revenue" is gross merchant fees, not what the bank keeps.**
The app ranks the churn and cross-sell lists by turnover times the merchant rate. In our own data, interchange (paid to the card issuer) is **54% of that figure**: AED 1.39 million a month gross against about AED 0.64 million net of interchange, and scheme fees are not deducted either. Ranking by net margin gives a different top five (13 of the top 15 overlap). The revenue is not shown on the cards, but it drives who appears and in what order.
*Not done yet: rank by margin over interchange, which the data already holds.*

**3. Our churn rule uses only volume and inactivity.**
ProSight says volume decline is "definitely not the only, best or earliest" indicator, and that useful models combine more than 40 signals, including service calls and requests. We have none of those in the data. The list is a reasonable first pass and the cards say what triggered them, but it will miss merchants that are unhappy before their volume falls, and it cannot detect price complaints. PaymentsJournal goes further and argues against prediction as the main answer, preferring to address root causes. That is a fair challenge to any churn model, ours included.

**4. The benefit is unproven.**
The uplift numbers in circulation (for example, the vendor Backbase repeating McKinsey and Accenture figures such as 22–30% productivity and 9% portfolio growth) come from other settings, are mostly vendor-quoted, and I did not verify them. None is evidence for this app. We have no pilot and the data is synthetic. Any claim of impact for this app would be an assumption.

**5. The attrition evidence is old and American.**
The two attrition studies are from 2017 and 2018 and describe US acquirers. They justify the problem, not the size of it in the UAE.

**6. A wrong date in our documents.**
Our rate-model script and project summary say the Visa table is "effective 19 December 2024". Visa's document says **19 October 2024**. The figures are right; the date is wrong. I have not changed it.

**7. Several limits we already knew now have outside context.**
- The "missed order cycles" signal is only inactive POS days; there is no order data.
- Only 16 suggestions are AI-written, and the model is off.
- The app's "current rate" and the rate model's cohort are synthetic, and I did not check typical UAE merchant discount rates against the market.
- Nine merchants have identical supplied turnover, which is a sign of how artificial the data is.

## 6. What I could not verify

- The McKinsey page behind the 25–30% figure (it timed out; the figure is confirmed only through a search extract and a vendor citation).
- The Central Bank's own AI guidance and Outsourcing Regulation text (blocked or dead links; I relied on press reports and law-firm summaries).
- The Morgan Stanley adoption figures (search extracts only).
- Any figure for the financing gap or for next-best-action uplift. I saw several, from vendors and a financial blog, and left them out.
- Whether any UAE bank already runs a merchant-RM co-pilot.

## 7. Suggested next steps from this check

1. Rank the lists by margin over interchange, not gross fees (finding 2).
2. Show the margin cost of a rate cut, and put a floor on reductions (finding 1).
3. Correct the date in the rate-model docstring and summary (finding 6).
4. Write down a governance owner and the intended use, for the compliance conversation (section 4).
5. Treat any impact figure for this app as an assumption until there is a pilot (finding 4).

## 8. Sources

| Source | Type | How used |
|---|---|---|
| [Visa UAE Interchange Reimbursement Fees, 19 Oct 2024 (PDF)](https://ae.visamiddleeast.com/content/dam/VCOM/regional/cemea/unitedarabemirates/home-page/support-consumer/visa-uae-interchange-reimbursement-fees-19-october-2024.pdf) | Primary (scheme) | Read in full |
| [Visa UAE Interchange Reimbursement Fees, May 2022 (PDF)](https://km.visamiddleeast.com/content/dam/VCOM/regional/cemea/unitedarabemirates/home-page/support-consumer/Visa-United-Arab-Emirates-interchange-reimbursement-fees.pdf) | Primary (scheme) | Read in full; shows the earlier rates |
| [The National, 23 Feb 2026, Central Bank AI guidelines](https://www.thenationalnews.com/business/banking/2026/02/23/uae-central-bank-issues-new-guidelines-on-the-use-of-ai-in-financial-sector/) | News | Opened |
| [PaymentsJournal, 19 Jul 2018](https://www.paymentsjournal.com/solving-the-merchant-attrition-problem/) | Trade press | Opened |
| [ProSight Financial Association, 5 Sep 2017](https://www.prosightfa.org/insights/merchant-attrition-to-merchant-addition-analytics-as-a-payments-catalyst/) | Industry association | Opened |
| [Gulf News, 6 Apr 2023, SMEs](https://gulfnews.com/amp/business/557000-smes-operated-in-uae-at-end-of-2022-minister-of-economy-1.94976713) | News | Opened |
| [Finance Middle East, interchange cap](https://www.financemiddleeast.com/opinion/cutting-payment-costs-a-new-chapter-for-uae-merchants/) | Opinion piece | Opened |
| [FinRAG-12B, arXiv 2605.05482](https://arxiv.org/abs/2605.05482) | Research preprint | Abstract opened |
| [NVIDIA NeMo Guardrails documentation](https://docs.nvidia.com/nemo/guardrails/latest/index.html) | Vendor documentation | Opened |
| [Backbase, "How AI is transforming relationship manager productivity"](https://www.backbase.com/blog/how-ai-is-transforming-relationship-manager-productivity-in-commercial-banking) | **Software vendor** | Opened; used only to see how it attributes its figures |
| [McKinsey, "Agentic AI is here"](https://www.mckinsey.com/industries/financial-services/our-insights/agentic-ai-is-here-is-your-banks-frontline-team-ready) | Consultancy | Search extract only; page timed out |
| [CDO Magazine, Morgan Stanley](https://www.cdomagazine.tech/aiml/98-of-morgan-stanley-wealth-management-advisors-use-its-ai-chatbot-with-improved-productivity-cao-explains-how); [CNBC, 26 Jun 2024](https://www.cnbc.com/2024/06/26/morgan-stanley-openai-powered-assistant-for-wealth-advisors.html) | Trade press, news | Search extracts only |
| [Gulf News, Emirates NBD](https://gulfnews.com/business/banking/emirates-nbd-embraces-ai-to-boost-productivity-1.96863997) | News | Search extract only |
| [Central Bank of the UAE rulebook, AI guidance note](https://rulebook.centralbank.ae/en/rulebook/guidance-note-consumer-protection-and-responsible-adoption-and-use-artificial-intelligence); [Outsourcing Regulation](https://rulebook.centralbank.ae/en/rulebook/outsourcing-regulation-banks) | Primary (regulator) | **Not read:** the first returned 403; the second was only seen in search results |
| Al Tamimi and Lexology summaries of the Outsourcing Regulation, found in search results | Law-firm summaries | Search extracts only |
